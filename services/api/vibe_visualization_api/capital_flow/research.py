from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx

from vibe_visualization_api.capital_flow.service import finite_number
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore
from vibe_visualization_api.capital_flow.etf_monitor import build_etf_monitor


ETF_SAMPLE = (
    ("510300.SH", "沪深300ETF", "宽基"),
    ("510500.SH", "中证500ETF", "宽基"),
    ("159915.SZ", "创业板ETF", "宽基"),
    ("512480.SH", "半导体ETF", "行业"),
    ("512880.SH", "证券ETF", "行业"),
    ("511010.SH", "国债ETF", "债券"),
    ("518880.SH", "黄金ETF", "商品"),
    ("513100.SH", "纳指ETF", "跨境"),
)
EXCHANGES = {"SSE": "上海", "SZSE": "深圳", "BSE": "北京"}


def iso_date(value) -> str | None:
    value = str(value or "").replace("-", "")
    if len(value) != 8:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def window_sum(points: list[dict], sessions: list[str], field: str, days: int) -> float | None:
    if len(sessions) < days:
        return None
    indexed = {row["date"]: row for row in points}
    values = [finite_number(indexed.get(day, {}).get(field)) for day in sessions[-days:]]
    return round(sum(values), 4) if all(value is not None for value in values) else None


def baseline(points: list[dict], sessions: list[str], field: str) -> dict:
    indexed = {row["date"]: row for row in points}
    latest = finite_number(indexed.get(sessions[-1], {}).get(field)) if sessions else None
    values = [finite_number(indexed.get(day, {}).get(field)) for day in sessions[-61:-1]]
    known = [value for value in values if value is not None]
    return {
        "samples": len(known), "expected": len(values),
        "percentile": round(sum(value <= latest for value in known) / len(known) * 100, 1)
        if latest is not None and len(known) >= 20 else None,
        "mean": round(sum(known) / len(known), 4) if len(known) >= 20 else None,
    }


def etf_strength(points: list[dict], sessions: list[str], days: int) -> dict:
    indexed = {row["date"]: row for row in points}
    dates = sessions[-days:]
    base_date = sessions[-days - 1] if len(sessions) > days else None
    base = indexed.get(base_date, {})
    def assets(row):
        shares, nav = finite_number(row.get("sharesWan")), finite_number(row.get("nav"))
        return shares * nav / 10000 if shares is not None and shares > 0 and nav is not None and nav > 0 else None
    base_assets = assets(base)
    flows, missing, splits = [], [], []
    for day in dates:
        row = indexed.get(day, {})
        if row.get("suspectedSplit"):
            splits.append(day)
        change = finite_number(row.get("shareChangeWan"))
        if assets(row) is None or change is None or row.get("suspectedSplit"):
            missing.append(day)
        else:
            # Compute before display rounding, important for small ETF share classes.
            flows.append(change * finite_number(row["nav"]) / 10000)
    complete = len(dates) == days and not missing and base_assets is not None
    reason = "交易日不足，无法取得完整窗口及期初规模" if len(sessions) <= days else (
        "期初份额或净值缺失／非正数" if base_assets is None else
        "窗口存在疑似份额折算，需公告核验" if splits else
        "窗口份额或同日净值缺失／无效，不补零" if missing else "")
    flow = sum(flows) if complete else None
    return {"days": days, "start": dates[0] if dates else None, "end": dates[-1] if dates else None,
            "baseDate": base_date, "baseAssetsYi": base_assets, "flowYi": round(flow, 8) if flow is not None else None,
            "strengthPct": round(flow / base_assets * 100, 6) if complete else None,
            "available": len(flows), "expected": days, "missingDates": missing, "splitDates": splits,
            "current": complete, "reason": reason}


def etf_analysis(code: str, name: str, category: str, rows: list[dict], sessions: list[str]) -> dict:
    indexed = {row["date"]: row for row in rows}
    previous = {day: sessions[index - 1] if index else None for index, day in enumerate(sessions)}
    points = []
    for day, row in sorted(indexed.items()):
        prior = indexed.get(previous.get(day)) or {}
        shares = finite_number(row.get("sharesWan"))
        old_shares = finite_number(prior.get("sharesWan"))
        nav = finite_number(row.get("nav"))
        old_nav = finite_number(prior.get("nav"))
        share_change = shares - old_shares if shares is not None and shares >= 0 and old_shares is not None and old_shares > 0 else None
        nav_change = (nav / old_nav - 1) * 100 if nav is not None and old_nav and old_nav > 0 else None
        suspected_split = bool(shares and old_shares and nav and old_nav
            and abs(shares / old_shares - 1) > .3 and abs(nav / old_nav - 1) > .2
            and (shares - old_shares) * (nav - old_nav) < 0
            and abs(shares * nav / (old_shares * old_nav) - 1) < .05)
        points.append({
            **row,
            "shareChangeWan": None if suspected_split else share_change,
            "shareChangePct": share_change / old_shares * 100 if share_change is not None and old_shares and not suspected_split else None,
            "flowYi": round(share_change * nav / 10_000, 4)
            if share_change is not None and nav is not None and nav > 0 and not suspected_split else None,
            "navChangePct": nav_change,
            "suspectedSplit": suspected_split,
        })
    expected = sessions[-1] if sessions else None
    latest = points[-1] if points else {}
    current = next((point for point in reversed(points) if point["date"] == expected), {})
    complete = current.get("flowYi") is not None
    return {
        "code": code, "name": name, "category": category, "currency": "CNY",
        "status": "ready" if complete else "partial" if points else "unavailable",
        "asOf": latest.get("date"), "expectedDate": expected,
        "latest": latest, "points": points,
        "summary": {"flow1dYi": window_sum(points, sessions, "flowYi", 1),
                    "flow5dYi": window_sum(points, sessions, "flowYi", 5),
                    "flow20dYi": window_sum(points, sessions, "flowYi", 20),
                    "baseline": baseline(points, sessions, "flowYi"),
                    "strength": {str(days): etf_strength(points, sessions, days) for days in (1, 5, 20)}},
        "note": "疑似份额折算，相关申赎估算已停止，需公告核验" if latest.get("suspectedSplit")
                else "数据日期落后于目标交易日" if expected and latest.get("date") != expected
                else "缺少前一交易日份额或当日净值，无法估算完整申赎" if not complete
                else "份额变化×当日净值；包含实物申赎和套利，不等于新增外部现金",
    }


def margin_analysis(rows: list[dict], sessions: list[str]) -> dict:
    by_date: dict[str, dict[str, dict]] = {}
    for row in rows:
        exchange = row.get("exchange_id")
        if exchange in EXCHANGES:
            by_date.setdefault(row["date"], {})[exchange] = row
    points = []
    for day, venues in sorted(by_date.items()):
        complete = set(venues) == set(EXCHANGES)
        def total(field):
            values = [finite_number(venues.get(exchange, {}).get(field)) for exchange in EXCHANGES]
            return round(sum(values) / 1e8, 4) if complete and all(value is not None for value in values) else None
        buying, repaying = total("rzmre"), total("rzche")
        points.append({"date": day, "exchanges": sorted(venues), "complete": complete,
                       "balanceYi": total("rzye"), "buyYi": buying, "repayYi": repaying,
                       "netYi": round(buying - repaying, 4) if buying is not None and repaying is not None else None,
                       "byExchange": [{"exchange": exchange, "name": EXCHANGES[exchange],
                            "balanceYi": finite_number(row.get("rzye")) / 1e8 if finite_number(row.get("rzye")) is not None else None}
                            for exchange, row in sorted(venues.items())]})
    expected = sessions[-1] if sessions else None
    latest = points[-1] if points else {}
    current = next((point for point in reversed(points) if point["date"] == expected), {})
    return {"status": "ready" if current.get("netYi") is not None else "partial" if points else "unavailable",
            "source": "Tushare margin / 沪深北交易所", "currency": "CNY", "unit": "亿元",
            "scope": list(EXCHANGES), "asOf": latest.get("date"), "expectedDate": expected,
            "latest": latest, "points": points,
            "summary": {"net1dYi": window_sum(points, sessions, "netYi", 1),
                        "net5dYi": window_sum(points, sessions, "netYi", 5),
                        "net20dYi": window_sum(points, sessions, "netYi", 20),
                        "baseline": baseline(points, sessions, "balanceYi")},
            "note": "沪深北缺一不做全市场合计；融资买入减偿还反映杠杆变化，不是市场现金净流入"}


class CapitalResearchService:
    def __init__(self, token: str, store: CapitalHistoryStore, *, client: httpx.AsyncClient | None = None,
                 today: date | None = None):
        self.token, self.store, self.client = token, store, client
        self.today = today or datetime.now(timezone(timedelta(hours=8))).date()
        self.start = (self.today - timedelta(days=150)).isoformat()
        self.end = (self.today - timedelta(days=1)).isoformat()
        self.gate = asyncio.Semaphore(3)

    async def _dataset(self, client, api, symbol, params, fields, date_field="trade_date", *, refresh=False, group_field=None, replace_window=False, cache_key=None):
        dataset = cache_key or api
        rows, run = await asyncio.to_thread(self.store.read, dataset, symbol, self.start, self.end)
        now = datetime.now(timezone.utc)
        cached = bool(run and run["start_date"] <= self.start and run["end_date"] >= self.end
                      and (now - datetime.fromisoformat(run["received_at"])).total_seconds() < 300)
        if cached and not refresh:
            return {"rows": rows, "status": run["status"], "reason": run["reason"],
                    "receivedAt": run["received_at"], "cached": True,
                    "usingSaved": bool(rows) and run["status"] != "ready"}
        status, reason, fetched = "unavailable", "Tushare 未配置", []
        if self.token:
            try:
                async with self.gate:
                    response = await client.post("https://api.tushare.pro", json={
                        "api_name": api, "token": self.token,
                        "params": {"start_date": self.start.replace("-", ""), "end_date": self.end.replace("-", ""), **params},
                        "fields": fields,
                    })
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") == 0:
                    data = payload.get("data") or {}
                    values_list = data.get("items") or []
                    if api == "fund_nav" and "ann_date" in (data.get("fields") or []):
                        ann_index = data["fields"].index("ann_date")
                        values_list = sorted(values_list, key=lambda values: str(values[ann_index] or ""))
                    for values in values_list:
                        row = dict(zip(data.get("fields") or [], values))
                        raw_date = row.get(date_field)
                        day = iso_date(f"{raw_date}01" if date_field == "month" else raw_date)
                        if day and self.start <= day <= self.end:
                            # Preserve exchange rows separately inside the daily observation.
                            if api == "margin":
                                row["date"] = day
                                fetched.append(row)
                            else:
                                fetched.append({**row, "date": day})
                    status, reason = ("ready", "") if fetched else ("empty", "接口成功，但查询区间未返回记录")
                else:
                    message = str(payload.get("msg") or "")
                    if "权限" in message or "没有接口" in message:
                        status, reason = "permission-denied", f"{api} 接口权限不足"
                    elif "每分钟" in message or "每小时" in message or "每天" in message:
                        status, reason = "rate-limited", f"{api} 调用频率受限"
                    else:
                        status, reason = "upstream-error", f"{api} 数据源返回异常"
            except (httpx.HTTPError, ValueError):
                status, reason = "upstream-error", f"{api} 请求失败"
        saved_rows = fetched
        if api == "margin" or group_field:
            grouped: dict[str, list] = {}
            for row in fetched:
                grouped.setdefault(row["date"], []).append(row)
            saved_rows = [{"date": day, group_field or "venues": values} for day, values in grouped.items()]
        received = now.isoformat()
        await asyncio.to_thread(self.store.save, dataset, symbol, saved_rows, start=self.start, end=self.end,
                                status=status, reason=reason, received_at=received, replace_window=replace_window)
        observations, _ = await asyncio.to_thread(self.store.read, dataset, symbol, self.start, self.end)
        # A failed update may use saved observations, but never hide the failure.
        return {"rows": observations, "status": status, "reason": reason, "receivedAt": received,
                "cached": False, "usingSaved": not fetched and bool(observations)}

    async def research(self, *, refresh=False, samples=None) -> dict:
        samples = ETF_SAMPLE if samples is None else samples
        owns = self.client is None
        client = self.client or httpx.AsyncClient(timeout=18, trust_env=False)
        try:
            calendar, margin, probe = await asyncio.gather(
                self._dataset(client, "trade_cal", "SSE", {"exchange": "SSE", "is_open": "1"}, "cal_date,is_open", "cal_date", refresh=refresh),
                self._dataset(client, "margin", "CN", {}, "trade_date,exchange_id,rzye,rzmre,rzche,rqye,rzrqye", refresh=refresh),
                self._dataset(client, "etf_share_size", samples[0][0], {"ts_code": samples[0][0]},
                              "trade_date,ts_code,total_share,nav,total_size", refresh=refresh),
            )
            sessions = sorted({row["date"] for row in calendar["rows"] if str(row.get("is_open")) == "1"})
            use_new = probe["status"] == "ready" and not probe.get("usingSaved")

            async def etf(code, name, category):
                if use_new:
                    shares = probe if code == samples[0][0] else await self._dataset(
                        client, "etf_share_size", code, {"ts_code": code}, "trade_date,ts_code,total_share,nav,total_size", refresh=refresh)
                    rows = [{"date": row["date"], "sharesWan": row.get("total_share"), "nav": row.get("nav")}
                            for row in shares["rows"]]
                    source = "Tushare etf_share_size"
                    feeds = [shares]
                else:
                    shares, nav = await asyncio.gather(
                        self._dataset(client, "fund_share", code, {"ts_code": code}, "ts_code,trade_date,fd_share", refresh=refresh),
                        self._dataset(client, "fund_nav", code, {"ts_code": code}, "ts_code,ann_date,nav_date,unit_nav", "nav_date", refresh=refresh),
                    )
                    navs = {row["date"]: row for row in nav["rows"]}
                    rows = [{"date": row["date"], "sharesWan": row.get("fd_share"),
                             "nav": navs.get(row["date"], {}).get("unit_nav"),
                             "navAnnDate": iso_date(navs.get(row["date"], {}).get("ann_date"))}
                            for row in shares["rows"]]
                    source = "Tushare fund_share + fund_nav"
                    feeds = [shares, nav]
                result = etf_analysis(code, name, category, rows, sessions)
                result.update({"source": source, "receivedAt": max(feed["receivedAt"] for feed in feeds),
                               "fetchStatus": "ready" if all(feed["status"] == "ready" for feed in feeds) else "degraded",
                               "sourceNote": "; ".join(dict.fromkeys(feed["reason"] for feed in feeds if feed["reason"])),
                               "usingSaved": any(feed.get("usingSaved") for feed in feeds)})
                if result["fetchStatus"] != "ready" and result["status"] == "ready":
                    result["status"] = "partial"
                if result["fetchStatus"] != "ready" or result["usingSaved"] or calendar["status"] != "ready" or calendar.get("usingSaved"):
                    for window in result["summary"]["strength"].values():
                        window["current"] = False
                        window["reason"] = "; ".join(filter(None, [window["reason"], "来源或交易日历更新未确认；数值仅作已存历史参考"]))
                return result

            etfs = await asyncio.gather(*(etf(*sample) for sample in samples))
            margin_rows = [venue for day in margin["rows"] for venue in day.get("venues", [])]
            leverage = margin_analysis(margin_rows, sessions)
            leverage.update({"fetchStatus": margin["status"], "sourceNote": margin["reason"],
                             "receivedAt": margin["receivedAt"], "usingSaved": margin.get("usingSaved", False)})
            if margin["status"] != "ready" and leverage["status"] == "ready":
                leverage["status"] = "partial"
            groups = []
            for category in dict.fromkeys(sample[2] for sample in samples):
                members = [item for item in etfs if item["category"] == category]
                def group_total(field):
                    values = [item["summary"][field] for item in members]
                    return round(sum(values), 4) if all(value is not None for value in values) else None
                groups.append({"category": category, "count": len(members),
                               "available": sum(item["status"] == "ready" for item in members),
                               "flow1dYi": group_total("flow1dYi"), "flow5dYi": group_total("flow5dYi"),
                               "flow20dYi": group_total("flow20dYi")})
            return {"schemaVersion": "newma-desk.capital-research.v1", "generatedAt": datetime.now(timezone.utc).isoformat(),
                    "expectedDate": sessions[-1] if sessions else None,
                    "calendar": {"status": calendar["status"], "sessions": len(sessions), "dates": sessions[-60:], "reason": calendar["reason"]},
                    "etfs": etfs, "groups": groups, "leverage": leverage,
                    "monitor": build_etf_monitor(etfs, sessions, calendar["status"] == "ready" and not calendar.get("usingSaved")),
                    "coverage": {"etfAvailable": sum(item["status"] == "ready" for item in etfs), "etfTotal": len(etfs),
                                 "sampleOnly": True, "primaryStatus": probe["status"], "primaryReason": probe["reason"]},
                    "notes": [f"{len(samples)}只ETF研究观察池，不代表全市场或整个资产类别；分类合计仅限观察池，研究分组不是官方分类",
                              "申赎是份额变化对应的金额估算，不是大单净额或外部现金流",
                              "交易日缺记录不补零，不跨缺失日拼出日流量；历史分位不是风险概率",
                              "原始来源按日保存；净值公告日、行情日和本地接收时间分别保留；不是历史可知时点回测"]}
        finally:
            if owns:
                await client.aclose()
