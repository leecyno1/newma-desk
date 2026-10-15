from __future__ import annotations

import asyncio
import zipfile
from xml.etree import ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import httpx

from vibe_visualization_api.capital_flow.research import CapitalResearchService, iso_date
from vibe_visualization_api.capital_flow.service import finite_number
from vibe_visualization_api.capital_flow.official_margin import SOURCES, fetch_official_rows


BOARD_FIELDS = "trade_date,ts_code,name,l_buy,l_sell,net_amount,reason"
SEAT_FIELDS = "trade_date,ts_code,exalter,side,buy,sell,net_buy,reason"
MARGIN_FIELDS = "ts_code,trade_date,rzye,rzmre,rzche,rqye,rzrqye"


def board_window(reason, day, sessions):
    if "连续三个交易日" in reason or "连续3个交易日" in reason or "三日" in reason:
        length, label = 3, "三交易日累计"
    elif "连续" not in reason and any(word in reason for word in ("日涨", "日跌", "日收盘", "日振幅", "日换手", "日成交", "当日")):
        length, label = 1, "单交易日"
    else:
        return {"label": "统计窗口未确认", "sessions": None, "start": None, "end": day}
    available = [value for value in sessions if value <= day]
    start = available[-length] if day in sessions and len(available) >= length else None
    return {"label": label, "sessions": length, "start": start, "end": day}


def board_disclosures(records, seats, symbol, day, sessions):
    records = [row for row in records if row.get("ts_code") == symbol and row.get("date") == day]
    seats = [row for row in seats if row.get("ts_code") == symbol and row.get("date") == day]
    groups = []
    for reason in sorted({str(row.get("reason") or "") for row in records}):
        disclosures = [row for row in records if str(row.get("reason") or "") == reason]
        unique = {tuple(finite_number(row.get(field)) for field in ("l_buy", "l_sell", "net_amount")) for row in disclosures}
        amounts = next(iter(unique)) if len(unique) == 1 else (None, None, None)
        selected = [row for row in seats if str(row.get("reason") or "") == reason]
        visible, named = [], {}
        patterns = [(str(row.get("exalter") or ""), *(finite_number(row.get(field)) for field in ("buy", "sell", "net_buy"))) for row in selected]
        removed = 0
        for index, row in enumerate(selected):
            name = str(row.get("exalter") or "未命名席位")
            ambiguous = not row.get("exalter") or any(label in name for label in ("机构专用", "机构专席", "未知", "交易单元"))
            buy, sell, net = [finite_number(row.get(field)) for field in ("buy", "sell", "net_buy")]
            key = (name, buy, sell, net)
            side = str(row.get("side"))
            if not ambiguous and key in named:
                existing = named[key]
                existing["sides"] = sorted(set([*existing["sides"], side]))
                existing["disclosureCount"] += 1
                removed += 1
                continue
            item = {"name": name, "sides": [side], "buyYuan": buy, "sellYuan": sell, "netYuan": net,
                    "ambiguousIdentity": ambiguous, "possibleRepeat": ambiguous and patterns.count(key) > 1,
                    "disclosureCount": 1, "residualYuan": round(net - (buy - sell), 2) if all(value is not None for value in (buy, sell, net)) else None,
                    "raw": row}
            visible.append(item)
            if not ambiguous:
                named[key] = item
        groups.append({"reason": reason or "理由未提供", "reasonKey": reason, "window": board_window(reason, day, sessions),
            "buyYuan": amounts[0], "sellYuan": amounts[1], "netYuan": amounts[2],
            "amountConflict": len(unique) > 1, "records": disclosures, "seats": visible,
            "rawSeatCount": len(selected), "repeatedNamedRows": removed,
            "ambiguousSeatRows": sum(row["ambiguousIdentity"] for row in visible), "aggregateSafe": False})
    return groups, len([row for row in seats if str(row.get("reason") or "") not in {group["reasonKey"] for group in groups}])


def margin_cases(rows, sessions, *, include_aligned=False):
    indexed = {row["date"]: row for row in rows}
    cases, checked = [], 0
    previous = {day: sessions[index - 1] if index else None for index, day in enumerate(sessions)}
    for day in sessions[-20:]:
        row, prior = indexed.get(day, {}), indexed.get(previous.get(day), {})
        values = [finite_number(prior.get("rzye")), *(finite_number(row.get(field)) for field in ("rzye", "rzmre", "rzche"))]
        if any(value is None for value in values):
            continue
        old, balance, buy, repay = values
        checked += 1
        expected = old + buy - repay
        residual = round(balance - expected, 2)
        if abs(residual) <= 1 and not include_aligned:
            continue
        cases.append({"date": day, "previousDate": previous[day], "previousBalanceYuan": old,
                      "balanceYuan": balance, "buyYuan": buy, "repayYuan": repay,
                      "expectedBalanceYuan": expected, "residualYuan": residual,
                      "size": "small" if abs(residual) <= 100 else "review", "raw": row, "previousRaw": prior})
    return cases, checked


def compare_margin(case, current, previous):
    rows = []
    for field, label, reference, primary in (
        ("rzye", "前日融资余额", previous, case["previousBalanceYuan"]),
        ("rzmre", "当日融资买入", current, case["buyYuan"]),
        ("rzche", "当日融资偿还", current, case["repayYuan"]),
        ("rzye", "当日融资余额", current, case["balanceYuan"]),
    ):
        value = finite_number(reference.get(field))
        difference = round(primary - value, 2) if value is not None else None
        rows.append({"field": label, "tushareYuan": primary, "referenceYuan": value, "differenceYuan": difference})
    status = "conflict" if any(row["differenceYuan"] is not None and abs(row["differenceYuan"]) > 1 for row in rows) else "agree" if all(row["referenceYuan"] is not None for row in rows) else "partial"
    residual = round(current["rzye"] - (previous["rzye"] + current["rzmre"] - current["rzche"]), 2) if all(row["referenceYuan"] is not None for row in rows) else None
    return {"status": status, "fields": rows, "referenceResidualYuan": residual,
            "available": sum(row["referenceYuan"] is not None for row in rows),
            "matched": sum(row["differenceYuan"] is not None and abs(row["differenceYuan"]) <= 1 for row in rows), "total": 4}


class CapitalEvidenceService(CapitalResearchService):
    async def _public_rows(self, client, dataset, key, start, end, request, normalize, *, refresh=False, fetch_rows=None):
        saved, run = await asyncio.to_thread(self.store.read, dataset, key, start, end)
        now = datetime.now(timezone.utc)
        if not refresh and run and run["start_date"] <= start and run["end_date"] >= end and (now - datetime.fromisoformat(run["received_at"])).total_seconds() < 300:
            return {"rows": saved, "status": run["status"], "reason": run["reason"], "usingSaved": bool(saved) and run["status"] not in {"ready", "empty"}, "receivedAt": run["received_at"]}
        rows, status, reason = [], "upstream-error", "公开来源请求失败"
        try:
            if fetch_rows:
                async with asyncio.timeout(12):
                    raw = await fetch_rows()
                payload = {}
            else:
                response = await request()
                response.raise_for_status()
                payload = response.json()
                raw = payload.get("result")
            if dataset == "eastmoney:margin":
                if payload.get("success") is not True:
                    if payload.get("code") == 9201:
                        raw = []
                    else:
                        raise ValueError("来源异常")
                else:
                    if (raw or {}).get("pages", 1) > 1:
                        raise ValueError("来源返回超过有界窗口，不能确认覆盖")
                    raw = (raw or {}).get("data") or []
            if not isinstance(raw, list) or any(not isinstance(row, dict) for row in raw):
                raise ValueError("来源记录结构异常")
            rows = [normalize(row) for row in raw]
            rows = [row for row in rows if row and start <= row["date"] <= end]
            status, reason = ("ready", "") if rows else ("empty", "目标证券及日期未返回记录，不套用其他日期")
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError, IndexError, zipfile.BadZipFile, ET.ParseError) as error:
            if fetch_rows and type(error) is ValueError:
                reason = str(error)
        received = now.isoformat()
        await asyncio.to_thread(self.store.save, dataset, key, rows, start=start, end=end, status=status,
                               reason=reason, received_at=received, replace_window=True)
        retained, _ = await asyncio.to_thread(self.store.read, dataset, key, start, end)
        return {"rows": retained, "status": status, "reason": reason, "usingSaved": bool(retained) and status not in {"ready", "empty"}, "receivedAt": received}

    async def _board(self, client, symbol, requested, refresh):
        selected = requested or self.end
        calendar_service = CapitalResearchService(self.token, self.store, client=client, today=self.today)
        calendar_service.start = (date.fromisoformat(selected) - timedelta(days=45)).isoformat()
        calendar_service.end = selected
        calendar = await calendar_service._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"},
                                                   "cal_date,is_open", "cal_date", refresh=refresh, cache_key="trade_cal:board")
        sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})
        day = requested or (sessions[-1] if sessions else selected)
        board_service = CapitalResearchService(self.token, self.store, client=client, today=self.today)
        board_service.start = board_service.end = day
        records, seats = await asyncio.gather(
            board_service._dataset(client, "top_list", f"{symbol}@{day}", {"ts_code": symbol, "trade_date": day.replace("-", "")}, BOARD_FIELDS, refresh=refresh, group_field="disclosures", replace_window=True),
            board_service._dataset(client, "top_inst", f"{symbol}@{day}", {"ts_code": symbol, "trade_date": day.replace("-", "")}, SEAT_FIELDS, refresh=refresh, group_field="seats", replace_window=True),
        )
        raw_records = [row for item in records["rows"] for row in item.get("disclosures", [])]
        raw_seats = [row for item in seats["rows"] for row in item.get("seats", [])]
        groups, unmatched = board_disclosures(raw_records, raw_seats, symbol, day, sessions if calendar["status"] == "ready" else [])
        return {"date": day, "dates": sessions[-20:], "calendarStatus": calendar["status"], "groups": groups,
                "recordsCoverage": {key: value for key, value in records.items() if key != "rows"},
                "seatsCoverage": {key: value for key, value in seats.items() if key != "rows"},
                "unmatchedSeats": unmatched, "aggregateSafe": False,
                "notes": ["只查询所选披露日；空结果不是近20日未上榜，也不是低风险",
                          "上榜理由逐项匹配；单日、三日及重叠理由不相加，三日窗口按交易日历推算，并非官方窗口ID",
                          "具名营业部相同金额的两侧披露合并展示；机构专用标签不能识别账户，保留披露而不合并机构总额",
                          "席位买入卖出金额元；榜单金额与订单分类资金不是同一总体，机构专用不等于基金持仓"]}

    async def _audit(self, client, code, symbol, selected, refresh):
        calendar, margin = await asyncio.gather(
            self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"}, "cal_date,is_open", "cal_date", refresh=refresh),
            self._dataset(client, "margin_detail", symbol, {"ts_code": symbol}, MARGIN_FIELDS, refresh=refresh),
        )
        sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})
        rows = [row for row in margin["rows"] if row.get("ts_code") == symbol]
        samples, checked = margin_cases(rows, sessions, include_aligned=True)
        cases = [sample for sample in samples if abs(sample["residualYuan"]) > 1]
        confirmed_inputs = calendar["status"] == margin["status"] == "ready" and not calendar["usingSaved"] and not margin["usingSaved"]
        start = sessions[-21] if len(sessions) >= 21 else sessions[0] if sessions else self.end
        def normalize(row):
            day = iso_date(str(row.get("DATE", ""))[:10])
            return {"date": day, "ts_code": symbol, "rzye": row.get("RZYE"), "rzmre": row.get("RZMRE"), "rzche": row.get("RZCHE")} if str(row.get("SCODE")) == code and day else None
        mirror = await self._public_rows(client, "eastmoney:margin", code, start, self.end,
            lambda: client.get("https://datacenter-web.eastmoney.com/api/data/v1/get", params={
                "reportName": "RPTA_WEB_RZRQ_GGMX", "columns": "DATE,SCODE,RZYE,RZMRE,RZCHE", "filter": f'(SCODE="{code}")(DATE>=\'{start}\')(DATE<=\'{self.end}\')',
                "pageSize": "100", "pageNumber": "1", "sortColumns": "DATE", "sortTypes": "-1", "source": "WEB", "client": "WEB"}), normalize, refresh=refresh) if cases else {"rows": [], "status": "not-requested", "reason": "无可追溯差异，不请求镜像", "usingSaved": False, "receivedAt": None}
        indexed = {row["date"]: row for row in mirror["rows"]} if mirror["status"] == "ready" and not mirror["usingSaved"] else {}
        for case in cases:
            case["mirrorComparison"] = compare_margin(case, indexed.get(case["date"], {}), indexed.get(case["previousDate"], {}))
        chosen = next((sample for sample in samples if sample["date"] == selected), None) if selected else max(cases, key=lambda case: abs(case["residualYuan"]), default=samples[-1] if samples else None)
        exchange = symbol.rsplit(".", 1)[-1]
        source = SOURCES[exchange]
        official = {"date": chosen["date"] if chosen else None, "status": "not-requested", "reason": "所选日期无完整两日融资样本" if selected and not chosen else "当前窗口无可核验样本", "comparison": None,
                    "sourceName": source["name"], "sourceUrl": source["url"], "missingFields": source["missingFields"]}
        if chosen and not confirmed_inputs:
            official["reason"] = "交易日历或融资来源更新失败，差异仅供旧记录参考，暂不作官方确认"
        if chosen and confirmed_inputs:
            async def fetch_day(day):
                dataset = {"SH": "sse:margin-official", "SZ": "szse:margin-official", "BJ": "bse:margin-official"}[exchange]
                return await self._public_rows(client, dataset, f"{code}@{day}", day, day, None, lambda row: row,
                    refresh=refresh, fetch_rows=lambda: fetch_official_rows(client, exchange, code, day))
            current, previous = await asyncio.gather(fetch_day(chosen["date"]), fetch_day(chosen["previousDate"]))
            ready = current["status"] == previous["status"] == "ready" and not current["usingSaved"] and not previous["usingSaved"]
            comparison = compare_margin(chosen, next(iter(current["rows"]), {}), next(iter(previous["rows"]), {})) if ready else None
            partial_verified = bool(comparison and source["missingFields"] and comparison["available"] == comparison["matched"] == 3)
            status = "verified" if comparison and comparison["status"] == "agree" else "partial-verified" if partial_verified else "conflict" if comparison and comparison["status"] == "conflict" else "unavailable"
            reason = "四项金额与交易所一致；官方原始数值亦存在该勾稽差额，原因仍待核查" if status == "verified" and abs(chosen["residualYuan"]) > 1 else "四项金额与交易所一致；所选样本未发现超过1元差额，不代表整体持仓无风险" if status == "verified" else "三项已披露金额与交易所一致；官方未单列融资偿还额，不反推补齐，不确认完整勾稽差额" if partial_verified else "交易所与Tushare金额冲突，保留双方" if status == "conflict" else "官方证券/日期未完整匹配或请求失败，不采用旧记录作确认"
            official = {**official, "date": chosen["date"], "previousDate": chosen["previousDate"], "status": status,
                        "reason": reason, "comparison": comparison, "current": current, "previous": previous}
        return {"expectedDate": sessions[-1] if sessions else None, "start": start, "end": self.end, "checked": checked,
                "expected": min(20, len(sessions)), "dates": [sample["date"] for sample in samples], "cases": cases, "smallDifferences": sum(case["size"] == "small" for case in cases),
                "reviewDifferences": sum(case["size"] == "review" for case in cases),
                "coverage": {key: value for key, value in margin.items() if key != "rows"}, "calendarStatus": calendar["status"], "confirmedInputs": confirmed_inputs,
                "mirror": {key: value for key, value in mirror.items() if key != "rows"}, "official": official,
                "notes": ["按元勾稽：前日融资余额+买入-偿还=当日余额；缺前一交易日不跨日计算",
                          "超过1元记录差异；1—100元为小额差异，超过100元单列待核查。这是显示分层，不是风险或重要性阈值",
                          "分发来源可能共享底稿；金额一致不证明业务原因。官方核验只覆盖所选差异日及前一日",
                          "官方数据确认数值差额不等于确认原因；不推定利息、调整或违法行为，需核查发布口径与更正"]}

    async def research(self, code, *, board_date=None, audit_date=None, refresh=False):
        suffix = "SH" if code.startswith("6") else "BJ" if code.startswith(("4", "8", "92")) else "SZ"
        symbol = f"{code}.{suffix}"
        client = self.client or httpx.AsyncClient(timeout=15, trust_env=False)
        try:
            board, audit = await asyncio.gather(self._board(client, symbol, board_date, refresh), self._audit(client, code, symbol, audit_date, refresh))
            return {"schemaVersion": "newma-desk.security-evidence.v1", "code": code, "symbol": symbol,
                    "generatedAt": datetime.now(timezone.utc).isoformat(), "board": board, "audit": audit}
        finally:
            if self.client is None:
                await client.aclose()
