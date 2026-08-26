"""Evidence-gated catalyst calendar for the integrated Research domain.

The module intentionally stays read-only and stateless.  User tracking lives in
Desk-managed storage, while this adapter only aggregates verifiable public
events and the governed direction windows published by Circle / Seven Cycle.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import hashlib
import os
import re
import threading
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import astock
import macro_monitor
import newsradar


SCHEMA_VERSION = "newma-desk.catalyst-calendar.v1"
_CACHE: dict[str, tuple[float, Any]] = {}
_CACHE_LOCK = threading.RLock()

_ANNOUNCEMENT_RULES = (
    ("regulatory", "监管事项", ("问询函", "监管函", "立案", "处罚", "警示函"), 30, "high"),
    ("corporate", "并购重组", ("重大资产重组", "并购", "收购", "购买资产"), 180, "high"),
    ("corporate", "再融资", ("定向增发", "向特定对象发行", "可转换公司债券", "发行股份"), 180, "high"),
    ("corporate", "股份回购", ("回购",), 90, "medium"),
    ("corporate", "股东大会", ("股东大会",), 45, "medium"),
    ("corporate", "分红实施", ("权益分派", "利润分配", "分红派息"), 14, "medium"),
    ("corporate", "股权激励", ("股权激励", "员工持股计划"), 90, "medium"),
    ("corporate", "合同与订单", ("中标", "重大合同", "框架协议"), 60, "medium"),
    ("corporate", "管理层变动", ("董事长辞职", "总经理辞职", "高级管理人员变动"), 30, "medium"),
)
_ANNOUNCEMENT_TERMINAL_TERMS = (
    "实施结果", "实施完毕", "完成的公告", "完成公告", "开户完成",
    "终止", "取消", "注销完成", "实施情况之",
)
_MACRO_INCLUDE_RE = re.compile(
    r"GDP|CPI|PPI|PMI|PCE|ISM|ADP|非农|就业|失业|初请|续请|通胀|物价|利率|LPR|M2|社融|信贷|央行|美联储|FOMC|议息|贸易|进出口|零售|工业增加值|固定资产投资|消费者信心|OPEC|G20|人大|政协|国务院|中央经济工作",
    re.I,
)
_MACRO_EXCLUDE_RE = re.compile(
    r"每日更新|每日仓单|库存-每日|钻井总数|ETF持仓|SPDR|iShares|COMEX.*库存",
    re.I,
)
_MACRO_FOCUS_RE = re.compile(
    r"非农|失业率|初请失业|GDP(?:季率|年率|年化|初值|终值|修正值)|"
    r"CPI(?:年率|月率)|PCE|PMI|ISM|LPR|MLF|M2货币供应|社会融资|"
    r"零售销售(?:月率|年率)|工业增加值|固定资产投资|贸易帐",
    re.I,
)
_MACRO_FOCUS_EXCLUDE_RE = re.compile(
    r"消费者信心|资产负债表|CPI预期|央行核心CPI|关联GDP|当周ADP",
    re.I,
)
_MAJOR_MACRO_REGIONS = {"中国", "美国", "欧元区", "日本"}
_CONCEPT_QUERY_ALIASES = {
    "地缘政治": ("地缘政治", "地缘", "中东", "乌克兰", "俄乌", "台海"),
    "战争": ("战争", "冲突", "袭击", "停火", "军事"),
    "光模块": ("光模块", "光通信", "光芯片", "CPO"),
}


def _macro_family(title: str) -> str:
    rules = (
        ("央行与利率", r"FOMC|议息|利率|LPR|MLF|央行|美联储"),
        ("就业", r"非农|ADP|就业"),
        ("失业与申领", r"失业|初请|续请"),
        ("GDP", r"GDP"),
        ("通胀", r"CPI|PCE|通胀|物价"),
        ("PPI", r"PPI"),
        ("PMI", r"PMI|ISM"),
        ("货币信贷", r"M2|社融|信贷"),
        ("零售", r"零售"),
        ("工业", r"工业增加值"),
        ("固定资产投资", r"固定资产投资"),
        ("贸易", r"贸易|进出口"),
        ("消费者信心", r"消费者信心"),
        ("政策会议", r"OPEC|G20|人大|政协|国务院|中央经济工作"),
    )
    return next((label for label, pattern in rules if re.search(pattern, title, re.I)), title[:24])


def _cached(key: str, ttl: int, fetch: Callable[[], Any]) -> Any:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    value = fetch()
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
    return value


def _iso(value: Any) -> str | None:
    if value is None or str(value) in {"", "NaT", "None", "nan"}:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text.replace("/", "-")).isoformat()
    except ValueError:
        return None


def _quarter_end(value: str) -> date | None:
    text = str(value or "").strip()
    if len(text) == 7 and text[4:6] == "-Q" and text[-1] in "1234":
        quarter = int(text[-1])
        month = quarter * 3
        next_month = date(int(text[:4]) + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
        return next_month - timedelta(days=1)
    if len(text) == 7 and text[4] == "-":
        try:
            year, month = (int(part) for part in text.split("-"))
            next_month = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
            return next_month - timedelta(days=1)
        except ValueError:
            return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    if month == 12:
        last_day = (date(year + 1, 1, 1) - timedelta(days=1)).day
    else:
        last_day = (date(year, month + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(value.day, last_day))


def _freshness(as_of: str, today: date) -> dict[str, Any]:
    parsed = _quarter_end(as_of)
    age_days = (today - parsed).days if parsed else None
    status = "unknown"
    if age_days is not None:
        status = "fresh" if age_days <= 45 else "stale"
    return {"status": status, "ageDays": max(age_days or 0, 0)}


def _urgency(days_away: int) -> str:
    if days_away <= 7:
        return "high"
    if days_away <= 30:
        return "medium"
    return "low"


def _score_impact(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.66:
        return "medium"
    return "low"


def _source_status(
    source_id: str,
    label: str,
    status: str,
    count: int,
    as_of: str,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "id": source_id,
        "label": label,
        "status": status,
        "count": count,
        "asOf": as_of,
        **({"error": error} if error else {}),
    }


def _report_periods(today: date) -> list[str]:
    year = today.year
    if today.month <= 4:
        return [f"{year - 1}年报", f"{year}一季"]
    if today.month <= 8:
        return [f"{year}半年报"]
    if today.month <= 10:
        return [f"{year}三季"]
    return [f"{year}年报"]


def _report_disclosure_events(
    symbols: set[str],
    today: date,
    horizon_end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    as_of = datetime.now(timezone.utc).isoformat()
    rows: list[tuple[str, dict[str, Any]]] = []
    errors: list[str] = []
    for period in _report_periods(today):
        try:
            frame = _cached(
                f"report-disclosure:{period}",
                6 * 3600,
                lambda period=period: astock.akshare_call(
                    "stock_report_disclosure",
                    market="沪深京",
                    period=period,
                ),
            )
            for row in frame.to_dict("records") if frame is not None and not frame.empty else []:
                rows.append((period, row))
        except Exception as exc:  # noqa: BLE001 - source failure is represented in the feed
            errors.append(f"{period}: {exc}")

    events: list[dict[str, Any]] = []
    for period, row in rows:
        symbol = str(row.get("股票代码") or "").zfill(6)
        if symbol not in symbols:
            continue
        actual = _iso(row.get("实际披露"))
        scheduled = next((
            value for value in (
                _iso(row.get("三次变更")),
                _iso(row.get("二次变更")),
                _iso(row.get("初次变更")),
                _iso(row.get("首次预约")),
            ) if value
        ), None)
        event_date = actual or scheduled
        if not event_date:
            continue
        parsed = date.fromisoformat(event_date)
        if parsed < today or parsed > horizon_end:
            continue
        name = str(row.get("股票简称") or symbol)
        original = _iso(row.get("首次预约"))
        revisions = [
            value for value in (
                _iso(row.get("初次变更")),
                _iso(row.get("二次变更")),
                _iso(row.get("三次变更")),
            ) if value
        ]
        changed = scheduled != original
        status = "confirmed" if actual else "upcoming"
        direction = "unchanged"
        if actual:
            direction = "actual"
        elif original and scheduled:
            direction = "advanced" if scheduled < original else ("delayed" if scheduled > original else "unchanged")
        events.append({
            "id": f"earnings:{symbol}:{period}:{event_date}",
            "type": "earnings",
            "date": event_date,
            "timePrecision": "date",
            "dateBasis": "official",
            "urgency": _urgency((parsed - today).days),
            "dateConfidence": "high" if actual else "medium",
            "dateChange": {
                "originalDate": original or event_date,
                "currentDate": event_date,
                "changeCount": len(revisions),
                "direction": direction,
            },
            "status": status,
            "title": f"{name} {period}披露",
            "summary": "实际披露日期" if actual else ("预约日期已变更，以最新预约为准" if changed else "巨潮资讯预约披露日期，临近时仍需复核"),
            "source": {
                "id": "cninfo-report-disclosure",
                "label": "巨潮资讯预约披露",
                "url": "http://www.cninfo.com.cn/new/commonUrl?url=data/yypl",
            },
            "evidenceIds": [f"cninfo:report-disclosure:{symbol}:{period}"],
            "asOf": as_of,
            "freshness": {"status": "live", "ageDays": 0},
            "confidence": {
                "level": "high" if actual else "medium",
                "score": 0.95 if actual else 0.72,
                "rationale": "实际披露" if actual else "预约日期可能调整，按最新变更字段排序",
            },
            "impactedAssets": [{"market": "CN", "symbol": symbol, "name": name}],
            "expectedDirection": "unknown",
            "nextAction": "核对业绩预告、关键经营指标和最新预约日期",
            "confirmationConditions": ["公司按预约日期披露定期报告"],
            "invalidationConditions": ["巨潮资讯出现新的预约变更或公司发布延期公告"],
            "importance": "high",
        })

    status = "ok" if events else ("unavailable" if errors and not rows else "empty")
    return events, _source_status(
        "cninfo-report-disclosure",
        "财报预约",
        status,
        len(events),
        as_of,
        "; ".join(errors)[:500] or None,
    )


def _lockup_events(
    symbols: set[str],
    today: date,
    horizon_end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    as_of = datetime.now(timezone.utc).isoformat()
    horizon_days = min(max((horizon_end - today).days, 1), 365)

    def fetch(symbol: str) -> tuple[str, dict[str, Any] | None, str | None]:
        try:
            data = _cached(
                f"lockup:{symbol}:{today.isoformat()}:{horizon_days}",
                1800,
                lambda: astock.lockup_expiry(
                    symbol,
                    trade_date=today.isoformat(),
                    forward_days=horizon_days,
                ),
            )
            return symbol, data, None
        except Exception as exc:  # noqa: BLE001
            return symbol, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(4, max(len(symbols), 1))) as pool:
        results = list(pool.map(fetch, sorted(symbols)))

    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for symbol, payload, error in results:
        if error:
            errors.append(f"{symbol}: {error}")
            continue
        for row in (payload or {}).get("upcoming") or []:
            event_date = _iso(row.get("date"))
            if not event_date:
                continue
            parsed = date.fromisoformat(event_date)
            ratio = float(row.get("ratio") or 0)
            able_shares = float(row.get("able_shares") or 0)
            event_type = str(row.get("type") or "限售股份")
            events.append({
                "id": f"lockup:{symbol}:{event_date}:{event_type}",
                "type": "lockup",
                "date": event_date,
                "timePrecision": "date",
                "dateBasis": "official",
                "urgency": _urgency((parsed - today).days),
                "dateConfidence": "high",
                "status": "upcoming",
                "title": f"{symbol} 限售股解禁",
                "summary": f"{event_type}；实际可流通约 {able_shares:,.2f} 万股；占比字段 {ratio:.2%}",
                "source": {
                    "id": "eastmoney-lockup",
                    "label": "东方财富解禁日历",
                    "url": "https://data.eastmoney.com/dxf/",
                },
                "evidenceIds": [f"eastmoney:lockup:{symbol}:{event_date}"],
                "asOf": as_of,
                "freshness": {"status": "live", "ageDays": 0},
                "confidence": {
                    "level": "high",
                    "score": 0.86,
                    "rationale": "公开解禁计划，实际流通数量仍可能因条件变化而调整",
                },
                "impactedAssets": [{"market": "CN", "symbol": symbol}],
                "expectedDirection": "unknown",
                "nextAction": "复核实际解禁数量、流通比例及公司最新公告",
                "confirmationConditions": ["到期后交易所与公司披露的实际可流通数量与计划一致"],
                "invalidationConditions": ["公司公告调整解禁日期、数量或解禁条件"],
                "importance": "high" if ratio >= 0.05 else ("medium" if ratio >= 0.01 else "low"),
            })

    status = "ok" if events else ("unavailable" if errors and len(errors) == len(results) else "empty")
    return events, _source_status(
        "eastmoney-lockup",
        "限售解禁",
        status,
        len(events),
        as_of,
        "; ".join(errors)[:500] or None,
    )


def _announcement_events(
    symbols: set[str],
    today: date,
    horizon_end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    as_of = datetime.now(timezone.utc).isoformat()

    def fetch(symbol: str) -> tuple[str, list[dict[str, Any]] | None, str | None]:
        try:
            rows = _cached(
                f"catalyst-announcements:{symbol}",
                900,
                lambda: astock.announcements(symbol, limit=20),
            )
            return symbol, rows, None
        except Exception as exc:  # noqa: BLE001
            return symbol, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(4, max(len(symbols), 1))) as pool:
        results = list(pool.map(fetch, sorted(symbols)))

    events: list[dict[str, Any]] = []
    clusters: dict[tuple[str, str], list[dict[str, Any]]] = {}
    errors: list[str] = []
    for symbol, rows, error in results:
        if error:
            errors.append(f"{symbol}: {error}")
            continue
        for row in rows or []:
            notice_date = _iso(row.get("date"))
            title = str(row.get("title") or "").strip()
            if not notice_date or not title:
                continue
            if any(term in title for term in _ANNOUNCEMENT_TERMINAL_TERMS):
                continue
            published = date.fromisoformat(notice_date)
            matched = next((rule for rule in _ANNOUNCEMENT_RULES if any(term in title for term in rule[2])), None)
            if matched is None:
                continue
            event_type, category, _, window_days, importance = matched
            window_end = published + timedelta(days=window_days)
            if window_end < today or published > horizon_end:
                continue
            clusters.setdefault((symbol, category), []).append({
                "published": published,
                "title": title,
                "url": str(row.get("url") or "https://data.eastmoney.com/notices/"),
                "type": event_type,
                "windowDays": window_days,
                "importance": importance,
            })

    for (symbol, category), rows in clusters.items():
        ordered_rows = sorted(rows, key=lambda row: row["published"])
        latest = ordered_rows[-1]
        window_end = latest["published"] + timedelta(days=latest["windowDays"])
        digest = hashlib.sha1(f"{symbol}:{category}".encode("utf-8")).hexdigest()[:12]
        events.append({
                "id": f"announcement:{symbol}:{digest}",
                "type": latest["type"],
                "date": window_end.isoformat(),
                "windowStart": latest["published"].isoformat(),
                "windowEnd": min(window_end, horizon_end).isoformat(),
                "timePrecision": "window",
                "dateBasis": "announcement-derived",
                "urgency": _urgency((window_end - today).days),
                "dateConfidence": "low",
                "status": "monitoring",
                "title": f"{symbol} {category}跟踪窗口",
                "summary": f"最新公告 {latest['published'].isoformat()}：{latest['title']}。近20条公告中合并 {len(ordered_rows)} 条同类进展；窗口用于跟踪后续正式日期或实施进展，不代表事件将在窗口结束日发生。",
                "source": {
                    "id": "eastmoney-announcement",
                    "label": "公司公告",
                    "url": latest["url"],
                },
                "evidenceIds": [
                    f"eastmoney:announcement:{symbol}:{hashlib.sha1(row['title'].encode('utf-8')).hexdigest()[:12]}"
                    for row in ordered_rows
                ],
                "asOf": as_of,
                "freshness": {"status": "live", "ageDays": max((today - latest["published"]).days, 0)},
                "confidence": {
                    "level": "medium",
                    "score": 0.68,
                    "rationale": "事件主题来自公司公告标题；具体实施日期尚未从公告正文结构化确认",
                },
                "impactedAssets": [{"market": "CN", "symbol": symbol}],
                "expectedDirection": "unknown",
                "nextAction": "跟踪后续正式日期、审议结果或实施进度公告",
                "confirmationConditions": ["公司或交易所披露明确实施日期、审议结果或后续进展"],
                "invalidationConditions": ["公司公告终止、取消、未通过审议或长期无后续进展"],
                "importance": latest["importance"],
            })

    status = "ok" if events else ("unavailable" if errors and len(errors) == len(results) else "empty")
    return events, _source_status(
        "eastmoney-announcement",
        "公司公告跟踪窗口",
        status,
        len(events),
        as_of,
        "; ".join(errors)[:500] or None,
    )


def _safe_cycle_base_url() -> str:
    raw = os.environ.get("NEWMA_DESK_SEVEN_CYCLE_WEB_URL", "http://127.0.0.1:4174").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("Seven Cycle URL must be an HTTP origin")
    return raw.rstrip("/") + "/"


def _load_cycle_research() -> dict[str, Any]:
    url = urljoin(_safe_cycle_base_url(), "data/cycle-research.json")
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Newma-Desk/0.1"})
    with urlopen(request, timeout=4) as response:  # noqa: S310 - URL is admin-controlled env
        import json

        return json.load(response)


def _cycle_events(
    today: date,
    horizon_end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        payload = _cached("seven-cycle:cycle-research", 900, _load_cycle_research)
    except Exception as exc:  # noqa: BLE001
        return [], _source_status(
            "seven-cycle",
            "周期叠加",
            "unavailable",
            0,
            fetched_at,
            str(exc)[:500],
        )

    events: list[dict[str, Any]] = []
    diagnostics = payload.get("diagnostics") or {}
    for cycle_id, diagnostic in diagnostics.items():
        publication = (diagnostic or {}).get("directionPublication") or {}
        if publication.get("status") != "limited" or not publication.get("gate", {}).get("passed"):
            continue
        as_of = str(publication.get("asOf") or "")
        window_start = _quarter_end(as_of)
        if not window_start:
            continue
        for horizon in publication.get("horizons") or []:
            if not horizon.get("qualified"):
                continue
            months = int(horizon.get("months") or 0)
            if months <= 0:
                continue
            window_end = _add_months(window_start, months)
            if window_end < today or window_end > horizon_end:
                continue
            probability = float(horizon.get("probability") or 0)
            accuracy = float(horizon.get("accuracy") or 0)
            outcome = str(horizon.get("outcome") or "状态变化")
            expected_direction = "negative" if "下行" in outcome else ("positive" if ("上行" in outcome or "风险偏好" in outcome) else "mixed")
            events.append({
                "id": f"cycle:{cycle_id}:{as_of}:{months}",
                "type": "macro",
                "date": window_end.isoformat(),
                "windowStart": window_start.isoformat(),
                "windowEnd": window_end.isoformat(),
                "timePrecision": "window",
                "dateBasis": "model-window",
                "urgency": _urgency((window_end - today).days),
                "dateConfidence": "low",
                "status": "monitoring",
                "title": f"{cycle_id} {horizon.get('label') or f'{months}个月'}状态观察窗",
                "summary": f"{publication.get('currentLabel') or '当前状态'}；{outcome}概率 {probability:.0%}，历史样本外方向准确率 {accuracy:.0%}",
                "source": {
                    "id": "seven-cycle",
                    "label": "Circle · 周期叠加",
                    "url": urljoin(_safe_cycle_base_url(), f"cycles?cycle={cycle_id}"),
                },
                "evidenceIds": [f"seven-cycle:{cycle_id}:{as_of}:{months}m"],
                "asOf": as_of,
                "freshness": _freshness(as_of, today),
                "confidence": {
                    "level": "high" if accuracy >= 0.78 else ("medium" if accuracy >= 0.66 else "low"),
                    "score": round(accuracy, 6),
                    "rationale": "仅发布通过递归样本外门槛的方向概率，不发布精确拐点",
                },
                "impactedAssets": [],
                "expectedDirection": expected_direction,
                "nextAction": "在窗口临近时更新周期数据并复核方向发布门槛",
                "confirmationConditions": ["后续滚动验证继续通过发布门槛，且同期限方向保持一致"],
                "invalidationConditions": ["后续验证未通过门槛、方向反转或源数据被标记为过期"],
                "importance": _score_impact(accuracy),
                "cycleContext": {
                    "cycleId": cycle_id,
                    "layer": publication.get("layer"),
                    "currentLabel": publication.get("currentLabel"),
                    "probability": probability,
                    "outcome": outcome,
                    "horizonMonths": months,
                    "exactCycleStatus": publication.get("exactCycleStatus"),
                    "assetForecastStatus": publication.get("assetForecastStatus"),
                    "caveat": publication.get("caveat"),
                },
            })

    return events, _source_status(
        "seven-cycle",
        "周期叠加",
        "ok" if events else "empty",
        len(events),
        str(payload.get("meta", {}).get("generated") or fetched_at),
    )


def _macro_calendar_events(
    today: date,
    horizon_end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
    requested_days = min(max((horizon_end - today).days, 1), 30)
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        rows, sources, gaps = macro_monitor._load_calendar(today, requested_days)
    except Exception as exc:  # noqa: BLE001 - source state is returned to the client
        return [], _source_status(
            "public-economic-calendar",
            "公开宏观经济日历",
            "unavailable",
            0,
            fetched_at,
            str(exc)[:500],
        ), [{"capability": "宏观经济日程", "reason": "公开日历源暂时不可用"}]

    clusters: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        title = str(row.get("title") or "").strip()
        if not title or _MACRO_EXCLUDE_RE.search(title) or not _MACRO_INCLUDE_RE.search(title):
            continue
        event_date = _iso(row.get("date"))
        if not event_date:
            continue
        parsed = date.fromisoformat(event_date)
        if parsed < today or parsed > horizon_end:
            continue
        region = str(row.get("region") or "全球")
        event_time = str(row.get("time") or "")
        clusters.setdefault((event_date, event_time, region, _macro_family(title)), []).append(row)

    events: list[dict[str, Any]] = []
    for (event_date, event_time, region, family), cluster in clusters.items():
        parsed = date.fromisoformat(event_date)
        representative = cluster[0]
        cluster_titles = " ".join(str(row.get("title") or "") for row in cluster)
        source_high = any(row.get("importance") == "high" for row in cluster)
        core_release = (
            region in _MAJOR_MACRO_REGIONS
            and bool(_MACRO_FOCUS_RE.search(cluster_titles))
            and not _MACRO_FOCUS_EXCLUDE_RE.search(cluster_titles)
        )
        importance = "high" if source_high or core_release else "medium"
        details = [region]
        if event_time:
            details.append(event_time)
        if len(cluster) > 1:
            details.append(f"合并 {len(cluster)} 项同批数据")
        details.extend(str(row.get("title") or "") for row in cluster[:3])
        for label, key in (("预期", "forecast"), ("前值", "previous")):
            value = representative.get(key)
            if value is not None and value != "":
                details.append(f"{label} {value:g}" if isinstance(value, float) else f"{label} {value}")
        source = representative.get("source") or {}
        digest = hashlib.sha1(f"{event_date}:{event_time}:{region}:{family}".encode("utf-8")).hexdigest()[:12]
        events.append({
            "id": f"macro-calendar:{digest}",
            "type": "macro",
            "date": event_date,
            "timePrecision": "date",
            "dateBasis": "aggregated-calendar",
            "urgency": _urgency((parsed - today).days),
            "dateConfidence": "medium",
            "status": "upcoming",
            "title": f"{region} {family}日程",
            "summary": " · ".join(details),
            "source": {
                "id": str(source.get("id") or "public-economic-calendar"),
                "label": str(source.get("label") or "公开宏观经济日历"),
                **({"url": source["url"]} if source.get("url") else {}),
            },
            "evidenceIds": [
                str(row.get("evidenceId") or f"macro-calendar:{event_date}:{index}")
                for index, row in enumerate(cluster)
            ],
            "asOf": str(representative.get("asOf") or fetched_at),
            "freshness": {"status": "live", "ageDays": 0},
            "confidence": {
                "level": "medium",
                "score": 0.74,
                "rationale": "日期来自公开经济日历聚合，临近发布前仍需回到官方机构复核",
            },
            "impactedAssets": [],
            "expectedDirection": "unknown",
            "nextAction": "核对官方发布时间、市场预期以及相关持仓与行业暴露",
            "confirmationConditions": ["官方机构按日程发布数据或会议结果"],
            "invalidationConditions": ["官方调整发布时间、取消发布或聚合源更正日程"],
            "importance": importance,
        })

    source_errors = [
        str(source.get("error"))
        for source in sources
        if source.get("error") and source.get("status") in {"unavailable", "partial"}
    ]
    status = "ok" if events and not source_errors else ("partial" if events else "empty")
    source = _source_status(
        "public-economic-calendar",
        "公开宏观经济日历",
        status,
        len(events),
        fetched_at,
        "; ".join(source_errors)[:500] or None,
    )
    normalized_gaps = []
    if not events:
        normalized_gaps.append({"capability": "宏观经济日程", "reason": "当前时间范围没有可用的中高重要性日程"})
    if gaps:
        normalized_gaps.append({"capability": "宏观官方源复核", "reason": "聚合日历已接入，官方日程源仍需逐步补齐"})
    return events, source, normalized_gaps


def _concept_signal_events(
    concepts: list[str],
    today: date,
    horizon_end: date,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, str]]]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    if not concepts:
        return [], _source_status("news-concept-radar", "概念主题雷达", "empty", 0, fetched_at), []

    events: list[dict[str, Any]] = []
    missing: list[str] = []
    for concept in concepts:
        pages = [
            newsradar.query_topics(query=query, sort="attention", limit=20)
            for query in _CONCEPT_QUERY_ALIASES.get(concept, (concept,))
        ]
        topic_map = {
            str(topic.get("id") or topic.get("headline") or topic.get("label")): topic
            for page in pages
            for topic in (page.get("items") or [])
        }
        topics = sorted(
            topic_map.values(),
            key=lambda topic: (topic.get("attention_score") or 0, topic.get("heat_score") or 0),
            reverse=True,
        )
        if not topics:
            missing.append(concept)
            continue
        top_topics = topics[:8]
        rising = [topic for topic in top_topics if topic.get("velocity_state") in {"new", "rising"}]
        attention = max(int(topic.get("attention_score") or 0) for topic in top_topics)
        source_names = sorted({str(source) for topic in top_topics for source in (topic.get("sources") or []) if source})
        signals = {str(topic.get("signal") or "watch") for topic in top_topics}
        if signals <= {"opportunity"}:
            expected_direction = "positive"
        elif signals <= {"risk"}:
            expected_direction = "negative"
        else:
            expected_direction = "mixed"
        importance = "high" if attention >= 60 or len(rising) >= 3 else ("medium" if attention >= 35 else "low")
        top = top_topics[0]
        top_item = (top.get("items") or [{}])[0]
        window_end = min(today + timedelta(days=14), horizon_end)
        digest = hashlib.sha1(concept.casefold().encode("utf-8")).hexdigest()[:12]
        events.append({
            "id": f"concept-signal:{digest}:{today.isoformat()}",
            "type": "industry",
            "date": window_end.isoformat(),
            "windowStart": today.isoformat(),
            "windowEnd": window_end.isoformat(),
            "timePrecision": "window",
            "dateBasis": "signal-window",
            "urgency": "high" if rising else "medium",
            "dateConfidence": "low",
            "status": "monitoring",
            "title": f"{concept} 主题催化观察窗",
            "summary": f"近 7 日命中 {len(topics)} 个主题，最高关注度 {attention}，{len(rising)} 个新出现或升温。当前焦点：{top.get('headline') or top.get('label') or concept}",
            "source": {
                "id": "news-concept-radar",
                "label": f"概念主题雷达 · {', '.join(source_names[:2]) or '公开资讯'}",
                **({"url": top_item["url"]} if top_item.get("url") else {}),
            },
            "evidenceIds": [str(topic.get("id")) for topic in top_topics if topic.get("id")],
            "asOf": str(next((page.get("generated_at_iso") for page in pages if page.get("generated_at_iso")), fetched_at)),
            "freshness": {"status": "live", "ageDays": 0},
            "confidence": {
                "level": "medium" if len(source_names) >= 2 else "low",
                "score": 0.7 if len(source_names) >= 2 else 0.55,
                "rationale": "主题来自多源新闻聚合与热度变化，只代表监测线索，不代表未来事件已确定",
            },
            "impactedAssets": [],
            "expectedDirection": expected_direction,
            "nextAction": "核对主题是否扩散到产业链、公司公告、订单与正式政策文件",
            "confirmationConditions": ["出现多源独立报道，且相关公司、机构或政策文件提供可核实进展"],
            "invalidationConditions": ["主题热度持续回落、仅有单一转述或后续出现否认与更正"],
            "importance": importance,
        })

    status = "ok" if events and not missing else ("partial" if events else "empty")
    gaps = ([{
        "capability": "概念主题覆盖",
        "reason": f"以下关键词暂未命中有效主题：{'、'.join(missing)}",
    }] if missing else [])
    return events, _source_status(
        "news-concept-radar",
        "概念主题雷达",
        status,
        len(events),
        fetched_at,
    ), gaps


def build_catalyst_feed(
    symbols: list[str],
    days: int = 180,
    include_cycles: bool = True,
    concepts: list[str] | None = None,
    include_macro: bool = True,
    today: date | None = None,
) -> dict[str, Any]:
    current = today or date.today()
    horizon_days = min(max(int(days), 14), 1095)
    horizon_end = current + timedelta(days=horizon_days)
    normalized = {
        symbol.strip()
        for symbol in symbols
        if symbol and symbol.strip().isdigit() and len(symbol.strip()) == 6
    }
    normalized = set(sorted(normalized)[:30])
    normalized_concepts = list(dict.fromkeys(
        concept.strip()[:40]
        for concept in (concepts or [])
        if concept and concept.strip()
    ))[:5]

    events: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []

    if normalized:
        report_events, report_source = _report_disclosure_events(normalized, current, horizon_end)
        events.extend(report_events)
        sources.append(report_source)
        lockup_events, lockup_source = _lockup_events(normalized, current, horizon_end)
        events.extend(lockup_events)
        sources.append(lockup_source)
        announcement_events, announcement_source = _announcement_events(normalized, current, horizon_end)
        events.extend(announcement_events)
        sources.append(announcement_source)
    else:
        as_of = datetime.now(timezone.utc).isoformat()
        sources.extend([
            _source_status("cninfo-report-disclosure", "财报预约", "empty", 0, as_of),
            _source_status("eastmoney-lockup", "限售解禁", "empty", 0, as_of),
            _source_status("eastmoney-announcement", "公司公告跟踪窗口", "empty", 0, as_of),
        ])

    if include_cycles:
        cycle_events, cycle_source = _cycle_events(current, horizon_end)
        events.extend(cycle_events)
        sources.append(cycle_source)

    if include_macro:
        macro_events, macro_source, macro_gaps = _macro_calendar_events(current, horizon_end)
        events.extend(macro_events)
        sources.append(macro_source)
        gaps.extend(macro_gaps)

    if normalized_concepts:
        concept_events, concept_source, concept_gaps = _concept_signal_events(
            normalized_concepts,
            current,
            horizon_end,
        )
        events.extend(concept_events)
        sources.append(concept_source)
        gaps.extend(concept_gaps)

    if not normalized and not normalized_concepts and not include_macro:
        gaps.append({"capability": "company-catalysts", "reason": "coverage_universe_empty"})
    for source in sources:
        if source["status"] in {"unavailable", "unsupported"}:
            gaps.append({"capability": source["id"], "reason": source["status"]})
    gaps.extend([
        {"capability": "股东大会准确日期", "reason": "当前仅从公告标题生成观察窗口，尚未解析公告正文日期"},
        {"capability": "产品发布与行业会议", "reason": "概念主题已提供监测窗口，正式活动日期仍缺稳定官方结构化源"},
        {"capability": "监管审批决定日", "reason": "仅覆盖公告触发的跟踪窗口，未覆盖全部审批节点"},
        {"capability": "地缘与历史参照", "reason": "当前以主题监测窗口承接，不把历史事件直接外推为未来日期"},
    ])

    deduplicated = {event["id"]: event for event in events}
    ordered = sorted(
        deduplicated.values(),
        key=lambda event: (event.get("date") or event.get("windowEnd") or "9999-12-31", event["id"]),
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": generated_at,
        "horizon": {"start": current.isoformat(), "end": horizon_end.isoformat(), "days": horizon_days},
        "coverage": {
            "markets": ["CN"],
            "symbols": sorted(normalized),
            "concepts": normalized_concepts,
            "includeMacro": include_macro,
        },
        "items": ordered,
        "sources": sources,
        "gaps": gaps,
        "disclaimer": "事件日期、周期方向与影响假设均需持续复核；本数据不构成投资建议。",
    }
