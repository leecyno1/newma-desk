"""Explicit daily A-share inputs; shared Tushare transport, no Desk imports."""

from __future__ import annotations

import math
import os
import re
import time
from datetime import date, datetime, timedelta
from threading import Lock
from zoneinfo import ZoneInfo

import requests


SOURCE = "tushare-daily"
_PAGE_SIZE = 1000
_CACHE_SECONDS = 300
_LOCK = Lock()
_CACHE: dict = {}
_CN = ZoneInfo("Asia/Shanghai")
_A_SHARE = re.compile(r"^(?:[036]\d{5}\.(?:SH|SZ)|[489]\d{5}\.BJ)$")
_SORT_FIELDS = {
    "amount": "amount", "changePct": "changePct", "turnoverPct": "turnoverPct",
    "volumeRatio": "volumeRatio", "marketCap": "marketCap", "pe": "pe", "pb": "pb",
}


class DailyScanUnavailable(RuntimeError):
    pass


def _number(value, scale=1):
    try:
        result = float(value)
    except (ValueError, TypeError):
        return None
    return result * scale if math.isfinite(result) else None


def _request(token: str, api: str, params: dict, fields: str, *, timeout=20) -> list[dict]:
    try:
        response = requests.post(
            "https://api.tushare.pro",
            json={"api_name": api, "token": token, "params": params, "fields": fields},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise DailyScanUnavailable(f"Tushare {api} 请求失败；未取得完整日频输入。") from None
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise DailyScanUnavailable(f"Tushare {api} 不可用，请检查接口权限或调用额度。")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DailyScanUnavailable(f"Tushare {api} 缺少数据结构。")
    columns, items = data.get("fields"), data.get("items")
    if (not isinstance(columns, list) or not set(fields.split(",")).issubset(columns)
            or not isinstance(items, list)
            or any(not isinstance(row, list) or len(row) != len(columns) for row in items)):
        raise DailyScanUnavailable(f"Tushare {api} 字段不完整。")
    return [dict(zip(columns, row)) for row in items]


def load_adjusted_daily_history(ts_code: str, *, limit: int, adjust: str, end: date | None = None) -> dict:
    """Match raw prices and factors by security/day; never fill missing factors."""
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise DailyScanUnavailable("复权日线备用源未配置 TUSHARE_TOKEN。")
    if not re.fullmatch(r"(?:6\d{5}\.SH|[03]\d{5}\.SZ|[489]\d{5}\.BJ)", ts_code) or adjust not in {"qfq", "hfq"}:
        raise DailyScanUnavailable("复权日线备用源仅支持明确的A股证券和复权口径。")
    completed = datetime.now(_CN).date() - timedelta(days=1)
    end = min(end or completed, completed)
    limit = min(max(int(limit), 40), 800)
    params = {"ts_code": ts_code, "end_date": end.strftime("%Y%m%d"), "limit": limit}

    def by_day(rows):
        result = {}
        for row in rows:
            text = str(row.get("trade_date") or "")
            try:
                day = datetime.strptime(text, "%Y%m%d").date()
            except ValueError:
                raise DailyScanUnavailable("日线或复权因子日期无效。") from None
            if (row.get("ts_code") != ts_code or not re.fullmatch(r"\d{8}", text)
                    or day > end or text in result):
                raise DailyScanUnavailable("日线或复权因子的证券、日期或唯一性不匹配。")
            result[text] = row
        return result

    prices = by_day(_request(token, "daily", params,
                            "ts_code,trade_date,open,high,low,close,vol,amount", timeout=4))
    if not prices:
        raise DailyScanUnavailable("复权日线备用源没有返回有效价格。")
    factors = by_day(_request(token, "adj_factor", {**params, "start_date": min(prices)},
                             "ts_code,trade_date,adj_factor", timeout=4))
    values = {day: _number(row.get("adj_factor")) for day, row in factors.items()}
    if any(values.get(day) is None or values[day] <= 0 for day in prices):
        raise DailyScanUnavailable("日线缺少同证券、同交易日的有效复权因子。")
    anchor_day = max(prices)
    anchor = values[anchor_day] if adjust == "qfq" else 1
    items = []
    for day, row in sorted(prices.items()):
        raw = {key: _number(row.get(key)) for key in ("open", "high", "low", "close", "vol", "amount")}
        if (any(value is None for value in raw.values())
                or any(raw[key] <= 0 for key in ("open", "high", "low", "close"))
                or raw["vol"] < 0 or raw["amount"] < 0):
            raise DailyScanUnavailable("复权日线包含缺失或无效的价格/成交数据。")
        ratio = values[day] / anchor
        items.append({
            "timestamp": int(datetime.strptime(day, "%Y%m%d").replace(tzinfo=_CN).timestamp() * 1000),
            **{key: raw[key] * ratio for key in ("open", "high", "low", "close")},
            "volume": raw["vol"], "turnover": raw["amount"] * 1000,
        })
    return {
        "items": items,
        "adjustmentAnchor": datetime.strptime(anchor_day, "%Y%m%d").date().isoformat() if adjust == "qfq" else None,
        "adjustmentMethod": "price * adj_factor / anchor_factor" if adjust == "qfq" else "price * adj_factor",
        "volumeUnit": "hand", "turnoverUnit": "CNY",
    }


def _table(token: str, api: str, params: dict, fields: str, *, timeout=None) -> dict[str, dict]:
    """Fetch every page before ranking, rejecting repeated pages and mixed dates."""
    result: dict[str, dict] = {}
    offset = 0
    while True:
        rows = _request(token, api, {**params, "limit": _PAGE_SIZE, "offset": offset}, fields,
                        **({"timeout": timeout} if timeout is not None else {}))
        for row in rows:
            code = str(row.get("ts_code") or "")
            if not code or code in result:
                raise DailyScanUnavailable(f"Tushare {api} 分页证券重复或身份缺失，不能确认覆盖范围。")
            if "trade_date" in params and row.get("trade_date") != params["trade_date"]:
                raise DailyScanUnavailable(f"Tushare {api} 返回了不同交易日，拒绝混合截面。")
            result[code] = row
        if len(rows) < _PAGE_SIZE:
            return result
        offset += len(rows)


def _load_snapshot(token: str, end: date) -> dict:
    # Always use a completed prior day; an intraday partial release is not a close.
    end_text = end.strftime("%Y%m%d")
    calendar = _request(token, "trade_cal", {
        "exchange": "SSE", "start_date": end_text, "end_date": end_text,
    }, "cal_date,is_open,pretrade_date")
    if len(calendar) != 1 or calendar[0].get("cal_date") != end_text:
        raise DailyScanUnavailable("交易日历未返回预期日期，不能确定日频扫描基准日。")
    row = calendar[0]
    day = end_text if row.get("is_open") == 1 else str(row.get("pretrade_date") or "")
    try:
        trade_date = datetime.strptime(day, "%Y%m%d").date()
    except ValueError:
        raise DailyScanUnavailable("交易日历缺少有效交易日。") from None
    if trade_date > end:
        raise DailyScanUnavailable("交易日历包含未完成交易日。")

    master = _table(token, "stock_basic", {"list_status": "L"}, "ts_code,name,industry,list_date")
    quotes = _table(token, "daily", {"trade_date": day},
                    "ts_code,trade_date,close,pct_chg,amount,vol,open,high,low,pre_close,change")
    basics = _table(token, "daily_basic", {"trade_date": day},
                   "ts_code,trade_date,turnover_rate,volume_ratio,pe,pb,total_mv,circ_mv")
    # stock_basic.industry is not a SW2021 security membership. Keep it only as
    # the original label; attach explicit hierarchy from the membership table.
    membership_state = "available"
    try:
        members = _table(token, "index_member_all", {"is_new": "Y"},
                         "ts_code,l1_code,l1_name,l2_code,l2_name,in_date,out_date,is_new",
                         timeout=2)
    except DailyScanUnavailable:
        members = {}
        membership_state = "unavailable"
    membership_received_at = datetime.now(_CN).isoformat(timespec="seconds")
    # Current master is not a point-in-time historical security universe.
    universe = {code: row for code, row in master.items()
                if _A_SHARE.fullmatch(code) and str(row.get("list_date") or "99999999") <= day}
    if not universe or not quotes:
        raise DailyScanUnavailable("Tushare 日频扫描无有效证券或日线，不能视为市场没有候选。")
    as_of = f"{trade_date.isoformat()}T15:00:00+08:00"
    items = []
    for code, info in sorted(universe.items()):
        quote = quotes.get(code)
        if not quote or (_number(quote.get("close")) or 0) <= 0:
            continue
        basic = basics.get(code, {})
        member = members.get(code, {})
        try:
            member_date = datetime.strptime(str(member.get("in_date") or ""), "%Y%m%d").date()
        except ValueError:
            member_date = None
        if (not member_date or member_date > trade_date or member.get("out_date")
                or member.get("is_new") != "Y"
                or not all(member.get(key) for key in ("l1_code", "l1_name", "l2_code", "l2_name"))):
            member = {}
        symbol, exchange = code.split(".")
        items.append({
            "symbol": symbol, "name": info.get("name") or symbol,
            "market": "CN", "exchange": exchange, "currency": "CNY", "timezone": "Asia/Shanghai",
            "price": _number(quote.get("close")), "change": _number(quote.get("change")),
            "changePct": _number(quote.get("pct_chg")), "prevClose": _number(quote.get("pre_close")),
            "open": _number(quote.get("open")), "high": _number(quote.get("high")),
            "low": _number(quote.get("low")), "volume": _number(quote.get("vol")),
            "amount": _number(quote.get("amount"), 1000),
            "turnoverPct": _number(basic.get("turnover_rate")), "volumeRatio": _number(basic.get("volume_ratio")),
            "marketCap": _number(basic.get("total_mv"), 10000),
            "floatMarketCap": _number(basic.get("circ_mv"), 10000),
            "pe": _number(basic.get("pe")), "pb": _number(basic.get("pb")),
            "industry": str(info.get("industry") or ""),
            "industryL1": str(member.get("l1_name") or ""),
            "industryL2": str(member.get("l2_name") or ""),
            "industryClassification": ({
                "taxonomy": "sw2021", "source": "tushare.index_member_all",
                "l1Code": member["l1_code"], "l2Code": member["l2_code"],
                "inDate": member_date.isoformat(), "receivedAt": membership_received_at,
                "pointInTime": False,
            } if member else {
                "taxonomy": "tushare_stock_basic", "source": "tushare.stock_basic",
                "pointInTime": False,
            }),
            "source": SOURCE, "sources": [SOURCE], "asOf": as_of,
        })
    if not items:
        raise DailyScanUnavailable("Tushare 日线与当前证券目录无法匹配，未取得候选。")
    return {
        "items": items, "source": SOURCE, "asOf": as_of,
        "receivedAt": datetime.now(_CN).isoformat(timespec="seconds"),
        "coverage": {
            "scope": "daily_a_share_ranked_top", "frequency": "daily", "realtime": False,
            "tradeDate": trade_date.isoformat(), "listedCount": len(universe),
            "quoteCount": len(items), "missingQuoteCount": len(universe) - len(items),
            "basicCount": sum(item["symbol"] + "." + item["exchange"] in basics for item in items),
            "fullSecurityMaster": False,
            "industryMembershipState": membership_state,
            "industryMembershipSource": "tushare.index_member_all",
            "industryMembershipCount": sum(bool(item["industryL1"]) for item in items),
            "missingIndustryMembershipCount": sum(not item["industryL1"] for item in items),
            "industryMembershipPointInTime": False,
            "industryMembershipNote": "当前申万成员归属，非历史点时分类；缺失时不使用stock_basic行业标签冒充申万归属。",
            "note": "前一已完成交易日日频截面，非实时；仅在已返回有效字段的证券中排序。缺失日线原因未核验，不能推断为停牌；当前上市目录不用于历史回测。",
        },
    }


def _daily_snapshot() -> dict:
    """Share the untruncated completed-day inputs with scan and breadth."""
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise DailyScanUnavailable("日频扫描已选择 Tushare，但尚未配置 TUSHARE_TOKEN。")
    end = datetime.now(_CN).date() - timedelta(days=1)
    with _LOCK:
        if (_CACHE.get("token") == token and _CACHE.get("end") == end
                and time.monotonic() - _CACHE.get("at", 0) < _CACHE_SECONDS):
            snapshot = _CACHE["snapshot"]
        else:
            snapshot = _load_snapshot(token, end)
            _CACHE.update(token=token, end=end, at=time.monotonic(), snapshot=snapshot)
    return snapshot


def daily_market_breadth() -> dict:
    snapshot = _daily_snapshot()
    groups = {}
    up = down = flat = missing_change = missing_classification = 0
    for item in snapshot["items"]:
        change = _number(item.get("changePct"))
        if change is None:
            missing_change += 1
        else:
            up += change > 0
            down += change < 0
            flat += change == 0
        identity = item.get("industryClassification") or {}
        code, name = identity.get("l1Code"), item.get("industryL1")
        if identity.get("taxonomy") != "sw2021" or not code or not name:
            missing_classification += 1
            continue
        row = groups.setdefault(code, {"code": code, "name": name,
            "up_count": 0, "down_count": 0, "flat_count": 0,
            "observed_count": 0, "missing_change_count": 0, "_sum": 0.0})
        if change is None:
            row["missing_change_count"] += 1
        else:
            row["up_count"] += change > 0
            row["down_count"] += change < 0
            row["flat_count"] += change == 0
            row["observed_count"] += 1
            row["_sum"] += change
    day = snapshot["asOf"][:10]
    source = "tushare.daily+index_member_all"
    rows = []
    for row in groups.values():
        count = row["observed_count"]
        row["change_pct"] = row.pop("_sum") / count if count else None
        if not count:
            row.update(up_count=None, down_count=None, flat_count=None)
        row.update(as_of=day, source=source, taxonomy="sw2021", point_in_time=False,
                   change_method="equal_weight_member_daily_pct")
        rows.append(row)
    rows.sort(key=lambda row: (row["change_pct"] is not None,
                              row["change_pct"] if row["change_pct"] is not None else 0), reverse=True)
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank if row["observed_count"] else None
    coverage = {**snapshot["coverage"], "scope": "all_returned_daily_quotes",
        "missingChangeCount": missing_change, "missingClassificationCount": missing_classification,
        "industryCount": len(rows), "pointInTime": False}
    partial = bool(coverage.get("missingQuoteCount") or missing_change or missing_classification)
    note = "全部已报价A股的日频统计，非Top榜样本；申万当前成员非历史点时。行业涨跌为成员等权均值，非申万指数涨幅；缺报价不推断为停牌。"
    total = up + down + flat
    ratio = up / max(down, 1)
    breadth = None if not total else "冰点" if up < 600 else "偏弱" if ratio < .7 else "中性" if ratio < 1.2 else "偏强" if ratio < 2.5 else "普涨"
    return {
        "sentiment": {"up": up if total else None, "down": down if total else None,
            "flat": flat if total else None, "breadth": breadth,
            "zt": None, "dt": None, "zt_real": None, "dt_real": None, "speculation": None,
            "date": day, "asOf": snapshot["asOf"], "receivedAt": snapshot["receivedAt"],
            "source": "tushare.daily", "scope": note, "realtime": False,
            "missingFields": ["zt", "dt", "zt_real", "dt_real"], "coverage": coverage},
        "industryBreadth": {"top": rows, "bottom": [], "total": len(rows), "as_of": day,
            "source": source, "coverage": coverage, "point_in_time": False,
            "data_state": "partial" if partial else "complete", "note": note},
    }


def scan_daily_quotes(*, sort="amount", order="desc", limit=100) -> dict:
    if sort not in _SORT_FIELDS or order not in {"asc", "desc"}:
        raise ValueError("不支持的日频扫描排序")
    snapshot = _daily_snapshot()
    field = _SORT_FIELDS[sort]
    eligible = [row for row in snapshot["items"] if row.get(field) is not None]
    # A missing metric is not zero and must never lead an ascending ranking.
    ranked = sorted(eligible, key=lambda row: row[field], reverse=order == "desc")
    limit = min(max(int(limit), 20), 200)
    return {
        **snapshot, "items": [dict(row) for row in ranked[:limit]],
        "market": "CN", "sort": sort, "order": order,
        "coverage": {**snapshot["coverage"], "requested": limit, "returned": min(limit, len(ranked)),
                     "rankableCount": len(ranked), "missingSortCount": len(snapshot["items"]) - len(ranked)},
    }
