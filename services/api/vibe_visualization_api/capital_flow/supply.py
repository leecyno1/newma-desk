from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from vibe_visualization_api.capital_flow.research import CapitalResearchService, iso_date
from vibe_visualization_api.capital_flow.service import finite_number


FEEDS = {
    "repurchase": ("回购披露", "ann_date", "124",
        "ts_code,ann_date,end_date,proc,exp_date,vol,amount,high_limit,low_limit"),
    "stk_holdertrade": ("股东增减持", "ann_date", "175",
        "ts_code,ann_date,holder_name,holder_type,in_de,change_vol,change_ratio,avg_price,begin_date,close_date"),
    "share_float": ("限售解禁", "float_date", "160",
        "ts_code,ann_date,float_date,float_share,float_ratio,holder_name,share_type"),
}
NOTES = [
    "回购金额为供应商披露值；计划不是实施，进展可能累计，缺少方案ID，不跨公告相加或计算回购净流入。",
    "增减持是披露记录，不是完整计划库；发生区间和公告日分开，不推断机构身份，不累加可能重叠的区间。",
    "解禁是潜在可流通供给，不是实际卖出；同股东、日期、股份类型的较早公告标记为旧披露，不重复计数。",
    "结构化记录不是公告原文；单位按接口字段与示例换算，投资前需复核公司公告。空记录不等于没有风险。",
]


def capacity_analysis(rows: list[dict], sessions: list[str], source_ready: bool) -> dict:
    indexed = {row["date"]: row for row in rows}
    window = sessions[-20:]
    volumes = [finite_number(indexed.get(day, {}).get("vol")) for day in window]
    amounts = [finite_number(indexed.get(day, {}).get("amount")) for day in window]
    complete = source_ready and len(window) == 20 and all(value is not None and value >= 0 for value in [*volumes, *amounts])
    shares = sum(volumes) * 100 / 20 if complete else None  # Tushare vol: hands, amount: thousand CNY.
    amount = sum(amounts) / 20 / 100000 if complete else None
    return {"status": "ready" if complete else "partial", "expectedDate": sessions[-1] if sessions else None,
            "samples": sum(value is not None for value in volumes), "expected": 20,
            "averageVolumeWan": shares / 1e4 if shares is not None else None, "averageTurnoverYi": amount,
            "participationPct": 5, "source": "Tushare daily / trade_cal · 未复权成交股数及成交额",
            "note": "过去20个交易日平均成交容量；5%参与率仅是承接场景假设，不预测卖出、成交价格或冲击成本"}


def supply_events(api: str, rows: list[dict], symbol: str, today: str) -> tuple[list[dict], int]:
    unique = {}
    matched = 0
    for row in rows:
        ann = iso_date(row.get("ann_date"))
        if row.get("ts_code") != symbol or (ann and ann > today):
            continue
        matched += 1
        key = tuple((field, str(row.get(field))) for field in FEEDS[api][3].split(","))
        unique[key] = row
    events = []
    for index, row in enumerate(unique.values()):
        def scaled(field, divisor):
            value = finite_number(row.get(field))
            return round(value / divisor, 6) if value is not None else None
        ann = iso_date(row.get("ann_date"))
        item = {"id": f"{api}:{index}", "kind": api, "annDate": ann, "holder": row.get("holder_name"),
                "amountYi": None, "sharesWan": None, "ratioPct": None, "beginDate": None,
                "endDate": None, "expiryDate": None, "superseded": False, "raw": row}
        if api == "repurchase":
            progress = str(row.get("proc") or "未提供")
            stage = {"预案": "计划", "董事会预案": "计划", "股东大会通过": "计划", "实施": "实施进展",
                     "实施中": "实施进展", "完成": "完成披露", "完成实施": "完成披露",
                     "停止实施": "已停止", "股东大会否决": "未通过"}.get(progress, "阶段待核验")
            item.update(label="股份回购", stage=stage, progress=progress,
                        eventDate=iso_date(row.get("end_date")) or ann,
                        endDate=iso_date(row.get("end_date")), expiryDate=iso_date(row.get("exp_date")),
                        amountYi=scaled("amount", 1e8), sharesWan=scaled("vol", 1e4),
                        note="金额与数量为该条披露值，可能是计划或累计进展；不做跨公告合计")
        elif api == "stk_holdertrade":
            direction = {"IN": "增持", "DE": "减持"}.get(row.get("in_de"), "增减持类型未知")
            begin, end = iso_date(row.get("begin_date")), iso_date(row.get("close_date"))
            item.update(label=direction, stage="区间披露·待核验" if begin and end and end <= today else "阶段待核验",
                        progress=direction, eventDate=end or ann, beginDate=begin, endDate=end,
                        sharesWan=scaled("change_vol", 1e4), ratioPct=finite_number(row.get("change_ratio")),
                        note="占流通股比例；不从数量、均价推算现金流，区间是否重叠需公告核验")
        else:
            day = iso_date(row.get("float_date"))
            item.update(label="限售解禁", stage="待解禁" if day and day > today else "已到解禁日" if day else "日期未知",
                        progress=row.get("share_type") or "类型未知", eventDate=day,
                        sharesWan=scaled("float_share", 1e4), ratioPct=finite_number(row.get("float_ratio")),
                        note="占总股本比例；到期不等于已流通，更不等于实际减持")
        events.append(item)
    if api == "share_float":
        latest = {}
        for item in events:
            if item["holder"] and item["annDate"]:
                key = (item["holder"], item["eventDate"], item["progress"])
                latest[key] = max(latest.get(key, ""), item["annDate"])
        for item in events:
            key = (item["holder"], item["eventDate"], item["progress"])
            item["superseded"] = bool(item["annDate"] and item["annDate"] < latest.get(key, ""))
    return sorted(events, key=lambda item: (item["eventDate"] or "", item["annDate"] or ""), reverse=True), matched - len(unique)


class CapitalSupplyService(CapitalResearchService):
    async def research(self, code: str, *, refresh=False) -> dict:
        # Announcement windows and future unlock dates must not inherit yesterday's market-data cutoff.
        self.start = (self.today - timedelta(days=365)).isoformat()
        self.end = (self.today + timedelta(days=90)).isoformat()
        today = self.today.isoformat()
        suffix = "SH" if code.startswith("6") else "BJ" if code.startswith(("4", "8", "92")) else "SZ"
        symbol = f"{code}.{suffix}"
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            async def feed(api, config):
                label, date_field, doc_id, fields = config
                result = await self._dataset(client, api, symbol,
                    {"ts_code": symbol, "end_date": (self.end if api == "share_float" else today).replace("-", "")},
                    fields, date_field, refresh=refresh, group_field="events", replace_window=True)
                raw = [row for day in result["rows"] for row in day.get("events", [])]
                items, removed = supply_events(api, raw, symbol, today)
                # Single-security bounded queries: flag source row limits, never imply exhaustive coverage.
                cap = 6000 if api == "share_float" else 3000 if api == "stk_holdertrade" else 2000
                capped = len(raw) >= cap
                return {"id": api, "label": label, "source": f"Tushare {api}",
                        "sourceUrl": f"https://tushare.pro/document/2?doc_id={doc_id}",
                        "status": "partial" if capped else result["status"],
                        "reason": "触及接口单次上限，覆盖不完整" if capped else result["reason"],
                        "receivedAt": result["receivedAt"], "usingSaved": result["usingSaved"],
                        "asOf": max((item["annDate"] for item in items if item["annDate"]), default=None),
                        "items": items, "count": len(items), "duplicatesRemoved": removed}
            market = CapitalResearchService(self.token, self.store, client=client, today=self.today)
            market.start = (self.today - timedelta(days=60)).isoformat()
            async def capacity():
                trading, daily = await asyncio.gather(
                    market._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"}, "cal_date,is_open", "cal_date", refresh=refresh),
                    market._dataset(client, "daily", symbol, {"ts_code": symbol}, "ts_code,trade_date,vol,amount", refresh=refresh))
                sessions = sorted({row["date"] for row in trading["rows"] if str(row.get("is_open")) == "1"})
                result = capacity_analysis([row for row in daily["rows"] if row.get("ts_code") == symbol], sessions, daily["status"] == "ready" and trading["status"] == "ready" and not daily["usingSaved"] and not trading["usingSaved"])
                return {**result, "reason": "; ".join(filter(None, [trading["reason"], daily["reason"]]))}
            *feeds, capacity_data = await asyncio.gather(*(feed(api, config) for api, config in FEEDS.items()), capacity())
            unlock_feed = next(feed for feed in feeds if feed["id"] == "share_float")
            for item in unlock_feed["items"]:
                volume = capacity_data["averageVolumeWan"]
                usable = unlock_feed["status"] == "ready" and not unlock_feed["usingSaved"] and item["stage"] == "待解禁" and not item["superseded"] and item["sharesWan"] is not None and volume and volume > 0
                item["capacityDaysAt5Pct"] = round(item["sharesWan"] / (volume * .05), 2) if usable else None
            return {"schemaVersion": "newma-desk.capital-supply.v1", "code": code, "symbol": symbol,
                    "generatedAt": datetime.now(timezone.utc).isoformat(), "asOf": today,
                    "window": {"start": self.start, "announcementEnd": today, "unlockEnd": self.end},
                    "feeds": feeds, "capacity": capacity_data, "notes": NOTES, "aggregateSafe": False}
        finally:
            if self.client is None:
                await client.aclose()
