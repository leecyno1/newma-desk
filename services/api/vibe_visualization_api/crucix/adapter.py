import calendar
import html
import json
import math
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlsplit


SNAPSHOT_CONTRACT = "newma-desk.crucix-intelligence.v1"
HEALTH_CONTRACT = "newma-desk.crucix-health.v1"
DEFAULT_STALE_AFTER_SECONDS = 2 * 60 * 60
_HTML_TAG = re.compile(r"<[^>]+>")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _record(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: Any, *, limit: int) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, Mapping)]


def _text(value: Any, *, limit: int = 300) -> str:
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return ""
    clean = html.unescape(str(value))
    clean = _HTML_TAG.sub(" ", clean)
    clean = _CONTROL.sub("", clean)
    return " ".join(clean.split())[:limit]


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if value == value and value not in {float("inf"), float("-inf")} else None


def _timestamp(value: Any) -> str | None:
    clean = _text(value, limit=64)
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _safe_url(value: Any) -> str | None:
    clean = _text(value, limit=2048)
    if not clean:
        return None
    parsed = urlsplit(clean)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return clean


def _series(value: Any, *, limit: int = 24) -> list[dict[str, Any] | int | float]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any] | int | float] = []
    for item in value[:limit]:
        numeric = _number(item)
        if numeric is not None:
            result.append(numeric)
            continue
        record = _record(item)
        point_value = _number(record.get("value", record.get("close")))
        if point_value is None:
            continue
        point: dict[str, Any] = {"value": point_value}
        point_date = _timestamp(record.get("date", record.get("timestamp")))
        if point_date:
            point["date"] = point_date
        result.append(point)
    return result


def _signals(value: Any, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:limit]:
        if isinstance(item, Mapping):
            text = _text(
                item.get("message", item.get("text", item.get("signal", item.get("title")))),
                limit=240,
            )
        else:
            text = _text(item, limit=240)
        if text and text not in result:
            result.append(text)
    return result


def _number_map(value: Any, *, limit: int = 40) -> dict[str, int | float]:
    result: dict[str, int | float] = {}
    for key, raw in list(_record(value).items())[:limit]:
        label = _text(key, limit=80)
        numeric = _number(raw)
        if label and numeric is not None:
            result[label] = numeric
    return result


_COUNT_LABELS = {
    "urgent_posts": ("展示的重点 OSINT 样本", "Telegram"),
    "thermal_total": ("热异常查询区域样本（可能重叠）", "FIRMS"),
    "air_total": ("航空查询区域样本（可能重叠）", "OpenSky"),
    "who_alerts": ("WHO 查询窗口报告", "WHO-DON"),
    "conflict_events": ("ACLED 报告事件样本", "ACLED"),
    "conflict_fatalities": ("ACLED 样本报告死亡数", "ACLED"),
    "news_count": ("RSS 展示样本（有上限）", "RSS"),
    "sources_ok": ("成功来源检查数（非市场风险）", "collection-health"),
}


def _count_endpoint(root, key, *, restored):
    """Project the engine's collection receipts; do not infer events from counts."""
    value, stamp, scope, unit, clocks = None, None, None, "records", []

    def count(value):
        return _number(value) is not None and 0 <= value <= 9007199254740991 and value % 1 == 0

    def total(rows, field):
        return sum(row[field] for row in rows) if isinstance(rows, list) and rows and all(
            isinstance(row, Mapping) and count(row.get(field)) for row in rows) else None

    if key == "urgent_posts":
        meta = _record(root.get("tg"))
        if meta.get("status") != "ok" or not isinstance(meta.get("urgent"), list):
            return None
        value, stamp, scope = len(meta["urgent"]), meta.get("collectedAt"), meta.get("scope")
    elif key == "thermal_total":
        meta = _record(root.get("thermalMeta"))
        if meta.get("status") != "ok":
            return None
        value, stamp, scope, unit = total(root.get("thermal"), "det"), meta.get("collectedAt"), meta.get("scope"), "detections"
    elif key == "air_total":
        meta, rows = _record(root.get("airMeta")), root.get("air")
        if meta.get("fallback") is not False or not isinstance(rows, list) or any(
            not isinstance(row, Mapping) or row.get("status") != "ok" for row in rows):
            return None
        clocks = [row.get("observedAt") for row in rows]
        value, stamp, scope, unit = total(rows, "total"), meta.get("timestamp"), meta.get("scope"), "regional-aircraft-samples"
    elif key == "who_alerts":
        meta = _record(root.get("whoMeta"))
        if meta.get("status") != "ok" or not all(_record(meta.get("window")).get(k) for k in ("start", "end")):
            return None
        value, stamp = meta.get("count"), meta.get("collectedAt")
        scope = {"source": "WHO-DON", "window": meta["window"], "limit": 100}
    elif key in {"conflict_events", "conflict_fatalities"}:
        meta = _record(root.get("acled"))
        if (meta.get("status") != "ok" or meta.get("basis") != "bounded-event-sample"
            or not all(_record(meta.get("period")).get(k) for k in ("start", "end"))
            or not count(meta.get("sampleLimit")) or _record(meta.get("coverage")).get("truncated") is not False):
            return None
        value, stamp = meta.get("totalEvents" if key == "conflict_events" else "totalFatalities"), meta.get("collectedAt")
        scope = {"source": "ACLED", "period": meta["period"], "limit": meta["sampleLimit"]}
        unit = "records" if key == "conflict_events" else "reported-fatalities"
    elif key == "news_count":
        meta, rows = _record(root.get("newsMeta")), _record(root.get("newsMeta")).get("items")
        historical_cache = restored and meta.get("mode") == "cache" and meta.get("status") in {"ok", "partial"}
        if (not isinstance(rows, list) or not rows or (not historical_cache and (meta.get("status") != "ok" or meta.get("cachedSources") != 0))
            or any(not isinstance(row, Mapping) or row.get("status") != "ok" or not _safe_url(row.get("url"))
                   or (row.get("cached") and not historical_cache)
                   or (historical_cache and (row.get("dataStatus") != "ok" or row.get("dataAsOf") != row.get("asOf"))) for row in rows)):
            return None
        clocks = [row.get("asOf") for row in rows]
        news = root.get("news")
        value, stamp = len(news) if isinstance(news, list) else _record(news).get("count"), meta.get("asOf")
        scope = {"source": "RSS", "feeds": sorted(row["url"] for row in rows), "limit": meta.get("limit"), "selection": meta.get("selection") or "regional-reserve-30d-v1"}
    elif key == "sources_ok":
        meta, rows = _record(root.get("meta")), root.get("health")
        if (not isinstance(rows, list) or not rows or len(rows) != meta.get("sourcesQueried")
            or any(not isinstance(row, Mapping) or not row.get("n") or row.get("status") not in {"ok", "error", "partial", "stale", "unknown"} for row in rows)):
            return None
        value = sum(row["status"] == "ok" for row in rows)
        if value != meta.get("sourcesOk"):
            return None
        stamp, scope, unit = meta.get("timestamp"), {"sources": sorted(row["n"] for row in rows)}, "source-checks"
    if not count(value) or not isinstance(scope, Mapping) or not scope:
        return None
    # Public query scope is kept intact; overlarge/invalid scope becomes a gap, not a truncated assertion.
    try:
        if len(json.dumps(scope, allow_nan=False)) > 32768:
            return None
    except (TypeError, ValueError):
        return None
    return {"value": value, "asOf": stamp, "scope": dict(scope), "unit": unit, "clocks": clocks}


def _comparison(root, now):
    """Read the source comparison, never calculate a new sweep or a risk rating."""
    state, delta = _record(root.get("deltaState")), _record(root.get("delta"))

    def instant(value):
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.astimezone(UTC) if parsed.tzinfo else None
        except ValueError:
            return None

    timestamp, batch = instant(state.get("timestamp")), instant(_record(root.get("meta")).get("timestamp"))
    status = state.get("status")
    valid_batch = timestamp is not None and timestamp == batch and timestamp <= now
    if not valid_batch or status not in {"current", "restored", "baseline", "unavailable"}:
        status = "unavailable"
    previous = instant(delta.get("previous"))
    if status in {"current", "restored"} and (instant(delta.get("timestamp")) != timestamp or previous is None or previous >= timestamp):
        status = "unavailable"
    result = {"status": status, "timestamp": _timestamp(state.get("timestamp")) if valid_batch else None,
              "previous": _timestamp(delta.get("previous")) if status in {"current", "restored"} else None,
              "freshness": _freshness(_timestamp(state.get("timestamp")) if valid_batch else None, now=now),
              "entries": [], "gaps": [], "changeCount": None, "reportedChangeCount": None, "reportedDirection": None,
              "note": "来源两批观测比较，非风险评级；恢复记录不是新采集。缺失与修订不算新变化，前值为零不计算相对变化；非完整点时或换月认证。"}
    if status not in {"current", "restored"}:
        return result
    signals, summary = _record(delta.get("signals")), _record(delta.get("summary"))
    if any(not isinstance(signals.get(key), list) for key in ("new", "escalated", "deescalated", "unchanged")):
        result.update(status="unavailable", note="来源比较记录不完整，不能判断无变化或风险下降。")
        return result
    if any(not isinstance(item, Mapping) for key in ("new", "escalated", "deescalated") for item in signals[key]):
        result.update(status="unavailable", note="来源变化条目无法核验，不能判断无变化或风险下降。")
        return result
    result["gaps"] = [{"key": _text(row.get("key"), limit=80), "reason": _text(row.get("reason"), limit=240)}
                      for row in _records(delta.get("comparisonGaps"), limit=80)]
    # Match the actual numeric series and units emitted by the existing delta engine.
    fred = {"vix": ("VIXCLS", "index points", "index points", 7),
            "hy_spread": ("BAMLH0A0HYM2", "percentage points", "percentage points", 7),
            "10y2y": ("T10Y2Y", "percentage points", "percentage points", 7),
            "fed_funds": ("DFF", "percent", "percentage points", 7),
            "10y_yield": ("DGS10", "percent", "percentage points", 7),
            "usd_index": ("DTWEXBGS", "index", "index points", 7),
            "mortgage": ("MORTGAGE30US", "percent", "percentage points", 14)}
    for item in _records(signals.get("escalated"), limit=40) + _records(signals.get("deescalated"), limit=40):
        key = _text(item.get("key"), limit=80)
        start, end, change = _number(item.get("from")), _number(item.get("to")), _number(item.get("change"))
        dates = [item.get("fromDate"), item.get("toDate")]
        if key in _COUNT_LABELS:
            endpoint = _count_endpoint(root, key, restored=status == "restored")
            parsed = [instant(value) for value in dates]
            # Primary-source aggregation clock differs from individual receipts; RSS enrichment can finish later.
            anchor = max(timestamp, parsed[1]) if parsed[1] else timestamp
            clocks = [instant(value) for value in endpoint["clocks"]] if endpoint else []
            valid = (endpoint is not None and all(parsed) and parsed[0] < parsed[1] <= now
                and 0 <= (anchor - parsed[0]).total_seconds() <= DEFAULT_STALE_AFTER_SECONDS
                and abs((parsed[0] - previous).total_seconds()) <= DEFAULT_STALE_AFTER_SECONDS
                and abs((parsed[1] - timestamp).total_seconds()) <= DEFAULT_STALE_AFTER_SECONDS
                and all(value and 0 <= (anchor - value).total_seconds() <= DEFAULT_STALE_AFTER_SECONDS for value in clocks)
                and item.get("countBasis") == "collection-sample-v1" and item.get("countScope") == endpoint["scope"]
                and instant(endpoint["asOf"]) == parsed[1] and start is not None and 0 <= start <= 9007199254740991 and start % 1 == 0
                and end == endpoint["value"] and start != end and change == end - start
                and item.get("unit") == endpoint["unit"] and item.get("changeUnit") == endpoint["unit"])
            pct = _number(item.get("pctChange"))
            expected = (end - start) / start * 100 if valid and start else None
            valid = valid and ((pct is None and expected is None) or (pct is not None and expected is not None and math.isclose(pct, expected, abs_tol=.051)))
            if not valid:
                result["gaps"].append({"key": key, "reason": "采集样本的范围、完整性、原时间、当前终点或计算未匹配；缺源不算零，减少不证明风险下降。"})
                continue
            label, source = _COUNT_LABELS[key]
            result["entries"].append({"key": key, "label": label, "from": start, "to": end, "change": change,
                "pctChange": pct, "fromDate": dates[0], "toDate": dates[1], "unit": endpoint["unit"], "changeUnit": endpoint["unit"],
                "direction": "up" if change > 0 else "down", "source": source, "basis": "collection-sample-v1",
                "kind": "collection-sample", "timeBasis": "collected", "countScope": endpoint["scope"],
                "note": "仅同范围采集样本变化，非事件发生、总体数量或风险下降依据；区域可能重叠，展示可能限量。",
                "currentEligible": status == "current" and result["freshness"]["status"] == "fresh" and (now - parsed[0]).total_seconds() <= DEFAULT_STALE_AFTER_SECONDS})
            continue
        observed, source, unit, change_unit, age_ok, observation_end = None, None, None, None, False, None
        if key in fred or key == "unemployment":
            monthly = key == "unemployment"
            series, unit, change_unit, days = ("LNS14000000", "percent", "percentage-points", 50) if monthly else fred[key]
            observed = next((row for row in _records(root.get("bls" if monthly else "fred"), limit=80) if row.get("id") == series), {})
            parsed = [_observation_period(value, monthly=monthly) for value in dates]
            evidence_ok = (parsed == dates and all(parsed) and item.get("seriesId") == series
                           and observed.get("date") == dates[1])
            if monthly:
                evidence_ok = evidence_ok and observed.get("frequency") == "monthly" and observed.get("unit") == unit and observed.get("seasonalAdjustment") == "seasonally-adjusted"
                age_ok = all(value and 1 <= (now.year * 12 + now.month) - (int(value[:4]) * 12 + int(value[5:7])) <= 2 for value in parsed)
                if parsed[1]:
                    year, month = map(int, parsed[1].split("-"))
                    observation_end = datetime(year, month, calendar.monthrange(year, month)[1], tzinfo=UTC)
            else:
                age_ok = all(value and 0 <= (now.date() - date.fromisoformat(value)).days <= days for value in parsed)
                observation_end = instant(f"{parsed[1]}T00:00:00Z") if parsed[1] else None
            source = "BLS" if monthly else "FRED"
        elif key in {"wti", "brent", "natgas", "gold", "silver"}:
            metal = key in {"gold", "silver"}
            identifier = "naturalGas" if key == "natgas" else key
            observed = next((row for row in _records(_record(root.get("metals" if metal else "energy")).get("observations"), limit=8) if row.get("id") == identifier), {})
            basis = _record(item.get("metalBasis" if metal else "energyBasis"))
            provenance = _record(observed.get("source"))
            actual = {field: observed.get(field) for field in ("id", "kind", "frequency", "unit")}
            actual.update(sourceId=provenance.get("id"), seriesId=provenance.get("seriesId"))
            unit = "USD/troy-ounce" if metal else "美元/百万英热单位" if key == "natgas" else "美元/桶"
            change_unit = unit
            quote = observed.get("kind") == "futures"
            parsed = [instant(value) if quote else _observation_period(value) for value in dates]
            endpoint = instant(observed.get("observedAt")) if quote else observed.get("period")
            evidence_ok = all(parsed) and parsed[1] == endpoint and dict(basis) == actual and actual["unit"] == unit
            age_ok = all(value is not None and 0 <= ((now - value).total_seconds() / 86400 if quote else (now.date() - date.fromisoformat(value)).days) <= 7 for value in parsed)
            observation_end = parsed[1] if quote else instant(f"{parsed[1]}T00:00:00Z") if parsed[1] else None
            source = _text(provenance.get("id"))
        else:
            result["gaps"].append({"key": key, "reason": "计数或状态变化缺少可核验的双期口径，未当作风险升降。"})
            continue
        valid = (evidence_ok and all(parsed) and parsed[0] < parsed[1] and observation_end is not None and observation_end <= timestamp
                 and start is not None and end is not None and start != end and change is not None
                 and end == _number(observed.get("value")) and math.isclose(change, end - start, rel_tol=1e-9, abs_tol=1e-9)
                 and item.get("unit") == unit and item.get("changeUnit") == change_unit)
        pct = _number(item.get("pctChange"))
        expected = (end - start) / abs(start) * 100 if valid and start != 0 and (key in fred or key == "unemployment" or start > 0 and end >= 0) else None
        valid = valid and ((pct is None and expected is None) or (pct is not None and expected is not None and math.isclose(pct, expected, abs_tol=.011)))
        if not valid:
            result["gaps"].append({"key": key, "reason": "双期日期、单位、当前终点或变化计算未匹配；修订与旧裸值不可作新异动。"})
            continue
        result["entries"].append({"key": key, "label": _text(item.get("label"), limit=120) or key,
            "from": start, "to": end, "change": change, "pctChange": pct, "fromDate": dates[0], "toDate": dates[1],
            **({"seriesId": item["seriesId"]} if item.get("seriesId") else {}), "unit": unit, "changeUnit": change_unit,
            "direction": "up" if change > 0 else "down", "source": source, "basis": "dated-source-comparison",
            "currentEligible": status == "current" and result["freshness"]["status"] == "fresh" and bool(age_ok)})
    if _records(signals.get("new"), limit=1):
        result["gaps"].append({"key": "source-notices", "reason": "来源新增提示未逐条核验，未转为新风险事件。"})
    result["changeCount"] = len(result["entries"])
    reported = _number(summary.get("totalChanges"))
    actual_count = sum(len(signals[key]) for key in ("new", "escalated", "deescalated"))
    if reported is not None and reported == actual_count:
        result["reportedChangeCount"] = int(reported)
    else:
        result["gaps"].append({"key": "source-summary", "reason": "来源报告总数缺失或与变化条目不一致，保留已核验数值，不判断完整变化数量。"})
    if not result["gaps"] and not any(row.get("kind") == "collection-sample" for row in result["entries"]) and summary.get("direction") in {"mixed", "risk-on", "risk-off"}:
        result["reportedDirection"] = summary["direction"]
    return result


def _freshness(
    as_of: str | None,
    *,
    now: datetime,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    degraded: bool = False,
) -> dict[str, Any]:
    if not as_of:
        return {
            "status": "unknown",
            "ageSeconds": None,
            "staleAfterSeconds": stale_after_seconds,
        }
    parsed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    age = (now.astimezone(UTC) - parsed).total_seconds()
    if age < 0:
        return {
            "status": "unknown",
            "ageSeconds": None,
            "staleAfterSeconds": stale_after_seconds,
        }
    age_seconds = int(age)
    return {
        "status": "stale" if degraded or age_seconds > stale_after_seconds else "fresh",
        "ageSeconds": age_seconds,
        "staleAfterSeconds": stale_after_seconds,
    }


def _indicators(value: Any, *, monthly: bool = False, now: datetime | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _records(value, limit=80):
        identifier = _text(item.get("id"), limit=40)
        label = _text(item.get("label", item.get("name")), limit=120)
        numeric = _number(item.get("value"))
        if not identifier and not label:
            continue
        record: dict[str, Any] = {
            "id": identifier,
            "label": label or identifier,
            "value": numeric,
            "date": _timestamp(item.get("date")),
            "momChangePct": _number(item.get("momChangePct")),
            "recent": _series(item.get("recent")),
        }
        if monthly:
            period = _observation_period(item.get("date"), monthly=True)
            record.update({
                "date": period, "period": period, "frequency": "monthly",
                "momChange": _number(item.get("momChange")),
                "yoyChangePct": _number(item.get("yoyChangePct")),
                "momPreviousPeriod": _observation_period(item.get("momPreviousPeriod"), monthly=True),
                "yoyPreviousPeriod": _observation_period(item.get("yoyPreviousPeriod"), monthly=True),
                "unit": _text(item.get("unit"), limit=40) or None,
                "changeUnit": _text(item.get("changeUnit"), limit=40) or None,
                "seasonalAdjustment": item.get("seasonalAdjustment") if item.get("seasonalAdjustment")
                    in {"seasonally-adjusted", "not-seasonally-adjusted"} else "unknown",
                "freshness": _observation_freshness(numeric, period, None, "monthly", now or datetime.now(UTC)),
            })
        result.append(record)
    return result


def _observation_period(value: Any, *, monthly: bool = False) -> str | None:
    text = _text(value, limit=64)
    try:
        if monthly and re.fullmatch(r"\d{4}-\d{2}", text):
            date.fromisoformat(f"{text}-01")
            return text
        parsed = date.fromisoformat(text) if len(text) == 10 else datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return parsed.isoformat()[:7] if monthly else parsed.isoformat()
    except ValueError:
        return None


def _observation_freshness(value, period, observed_at, frequency, now, *, degraded=False):
    # These are conservative update windows, not claims about publication schedules.
    window = {"monthly": 50, "weekly": 14, "daily": 7, "quote": 3}.get(frequency, 7) * 86400
    reference = observed_at
    if not reference and period:
        if frequency == "monthly":
            year, month = map(int, period.split("-"))
            reference = f"{period}-{calendar.monthrange(year, month)[1]:02d}T00:00:00Z"
        else:
            reference = f"{period}T00:00:00Z"
    if value is None or (reference and datetime.fromisoformat(reference.replace("Z", "+00:00")) > now):
        reference = None
    result = _freshness(reference, now=now, stale_after_seconds=window)
    if degraded and value is not None:
        result["status"] = "stale"
    return result


def _dated_history(value, latest_period, now, *, monthly=False):
    """Only source-dated observations; scalar sparklines cannot supply dates."""
    if not latest_period:
        return []
    ceiling = min(latest_period, now.date().isoformat()[:7] if monthly else now.date().isoformat())
    points = {}
    for row in _records(value, limit=120):
        period = _observation_period(row.get("period", row.get("date")), monthly=monthly)
        numeric = _number(row.get("value"))
        if period and period <= ceiling and numeric is not None:
            points.setdefault(period, numeric)
    return [{"period": period, "value": points[period]} for period in sorted(points)]


def _energy_observations(energy, source_items, now):
    raw = {item.get("id"): item for item in _records(energy.get("observations"), limit=4)}
    result = []
    for identifier, legacy_key, label in (("wti", "wti", "WTI"), ("brent", "brent", "Brent"),
                                          ("naturalGas", "natgas", "天然气"), ("crudeStocks", "crudeStocks", "原油库存")):
        item = raw.get(identifier, {})
        source = _record(item.get("source"))
        value = _number(item.get("value")) if item else _number(energy.get(legacy_key))
        period = _observation_period(item.get("period"))
        observed_at = _timestamp(item.get("observedAt"))
        frequency = item.get("frequency") if item.get("frequency") in {"daily", "weekly", "quote"} else "unknown"
        degraded = any(row["source"] == source.get("collectorId", source.get("id")) and row["status"] in {"error", "stale", "unknown"} for row in source_items)
        provenance = {"id": _text(source.get("id")), "label": _text(source.get("label")),
                      "seriesId": _text(source.get("seriesId")), "url": _safe_url(source.get("url"))} if source else None
        if provenance:
            for field in ("collectorId", "originalSource", "originalSeriesId", "fallbackReason"):
                if source.get(field):
                    provenance[field] = _text(source[field])
            if source.get("originalUrl"):
                provenance["originalUrl"] = _safe_url(source["originalUrl"])
        result.append({
            "id": identifier, "label": _text(item.get("label")) or f"{label}（口径待核验）", "value": value,
            "kind": item.get("kind") if item.get("kind") in {"spot", "futures", "inventory"} else "unknown",
            "unit": _text(item.get("unit"), limit=80) or None, "frequency": frequency,
            "period": period, "observedAt": observed_at,
            "history": _dated_history(item.get("history"), period, now) if frequency in {"daily", "weekly"} else [],
            "source": provenance,
            "note": _text(item.get("note")) or "旧快照未保留来源、报价类型与数据时间；不能视为 EIA 现货或实时价格。",
            "freshness": _observation_freshness(value, period, observed_at, frequency, now, degraded=degraded),
        })
    return result



def _metal_observations(metals, source_items, now):
    raw = {item.get("id"): item for item in _records(metals.get("observations"), limit=2)}
    result = []
    for identifier, symbol, label in (("gold", "GC=F", "黄金"), ("silver", "SI=F", "白银")):
        item = raw.get(identifier, {})
        source = _record(item.get("source"))
        value = _number(item.get("value")) if item else _number(metals.get(identifier))
        original_time = _text(item.get("observedAt"))
        observed = _timestamp(original_time) if re.search(r"T.*(?:Z|[+-]\d{2}:\d{2})$", original_time) else None
        verified = (item.get("kind") == "futures" and item.get("frequency") == "quote"
                    and item.get("unit") == "USD/troy-ounce"
                    and source.get("id") == "YFinance" and source.get("seriesId") == symbol)
        freshness = _freshness(observed if verified and value is not None else None,
                               now=now, stale_after_seconds=7 * 86400,
                               degraded=any(row["source"] == "YFinance" and row["status"] in {"error", "stale"}
                                            for row in source_items))
        result.append({"id": identifier, "label": label, "value": value,
                       "kind": item.get("kind") if item.get("kind") == "futures" else "unknown",
                       "frequency": "quote" if item.get("frequency") == "quote" else "unknown",
                       "unit": _text(item.get("unit"), limit=80) or None,
                       "observedAt": observed, "basisVerified": bool(verified and observed and value is not None), "freshness": freshness,
                       "source": {"id": _text(source.get("id")), "seriesId": _text(source.get("seriesId")),
                                  "url": _safe_url(source.get("url"))} if source else None,
                       "prevClose": _number(item.get("prevClose")),
                       "previousCloseBasis": item.get("previousCloseBasis") if item.get("previousCloseBasis") in {"provider", "daily-bars"} else None,
                       "previousCloseDate": None, "history": [],
                       "note": "连续期货可能换月，不是现货或实物价格；前收日期未知，不作为已核实的今日收益。"
                               if verified else "旧值或报价口径未核验，不补单位、来源或报价时间。"})
    return result


def _supply_observation(raw, source_items, now):
    if not raw:
        return None
    value = _number(raw.get("value"))
    period = _observation_period(raw.get("date"), monthly=True)
    vintage = _text(raw.get("vintage"), limit=80) or None
    source = _record(raw.get("source"))
    status = raw.get("status") if raw.get("status") in {"ok", "partial", "error", "no_data"} else "unknown"
    verified = (value is not None and period is not None and vintage is not None
                and raw.get("frequency") == "monthly" and raw.get("unit") == "standard-deviations"
                and source.get("id") == "GSCPI" and source.get("seriesId") == "GSCPI"
                and status in {"ok", "partial"})
    points = {}
    for row in _records(raw.get("history"), limit=120):
        month = _observation_period(row.get("period", row.get("date")), monthly=True)
        numeric = _number(row.get("value"))
        revision = _text(row.get("vintage"), limit=80) or None
        if (not month or not period or month > period or month >= now.strftime("%Y-%m")
                or numeric is None or revision != vintage):
            continue
        if month in points and points[month] != numeric:
            points[month] = None
        else:
            points.setdefault(month, numeric)
    history = [{"period": month, "value": number, **({"vintage": vintage} if vintage else {})}
               for month, number in sorted(points.items()) if number is not None]
    return {"value": value, "date": period, "period": period, "dateBasis": "period",
            "unit": _text(raw.get("unit"), limit=80) or None,
            "frequency": "monthly" if raw.get("frequency") == "monthly" else "unknown",
            "vintage": vintage, "vintageBasis": "source-column-id" if vintage else "unknown",
            "status": status, "rejected": _number(raw.get("rejected")), "missing": _number(raw.get("missing")),
            "collectedAt": _timestamp(raw.get("collectedAt")), "basisVerified": verified,
            "source": {"id": _text(source.get("id")), "seriesId": _text(source.get("seriesId")),
                       "url": _safe_url(source.get("url"))} if source else None,
            "freshness": _observation_freshness(value, period, None, "monthly", now,
                degraded=status == "error" or any(row["source"] == "GSCPI" and row["status"] in {"error", "stale"} for row in source_items)),
            "interpretation": _text(raw.get("interpretation"), limit=240), "history": history,
            "note": "月度统计期不是发布日期；修订列标识不是已核实的发布日期或点时版本；零代表历史均值。"}


def _treasury_snapshot(value: Any, now: datetime) -> dict[str, Any]:
    raw = _record(value)
    coverage = _record(raw.get("coverage"))

    def amount(value):
        text = _text(value)
        return text if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text) and _number(float(text)) is not None else None

    debt = []
    for row in _records(raw.get("debt"), limit=5):
        period = _observation_period(row.get("date"))
        total = amount(row.get("totalDebt"))
        debt.append({"date": period, "totalDebt": total, "publicDebt": amount(row.get("publicDebt")),
                     "intragovDebt": amount(row.get("intragovDebt")), "unit": "USD", "frequency": "daily",
                     "freshness": _observation_freshness(float(total) if total is not None else None,
                         period, None, "daily", now, degraded=_record(coverage.get("debt")).get("status") in ("error", "partial"))})
    rates = []
    for row in _records(raw.get("interestRates"), limit=100):
        period = _observation_period(row.get("date"), monthly=True)
        rate = _number(row.get("rate"))
        basis = row.get("basis") == "outstanding-debt-average-interest-rate"
        rates.append({"date": period, "security": _text(row.get("security")),
                      "securityType": _text(row.get("securityType")), "rate": rate,
                      "unit": "percent" if basis else None, "frequency": "monthly",
                      "basis": "outstanding-debt-average-interest-rate" if basis else "unknown",
                      "freshness": _observation_freshness(rate, period, None, "monthly", now,
                          degraded=_record(coverage.get("interestRates")).get("status") in ("error", "partial"))})
    latest = debt[0] if debt else {}
    total = latest.get("totalDebt", amount(raw.get("totalDebt")))
    period = latest.get("date", _observation_period(raw.get("date")))
    if not period and total is not None and float(total) == 0:
        total = None  # Old synthesis used '0' for failed collection.
    return {"totalDebt": total, "date": period, "unit": "USD", "frequency": "daily",
            "freshness": latest.get("freshness") or _observation_freshness(
                float(total) if total is not None else None, period, None, "daily", now),
            "status": _text(raw.get("status")) or "unknown", "collectedAt": _timestamp(raw.get("collectedAt")),
            "debt": debt, "interestRates": rates,
            "coverage": {key: {"status": _text(_record(coverage.get(key)).get("status")) or "unknown",
                               "latestDate": _observation_period(_record(coverage.get(key)).get("latestDate")),
                               "count": _number(_record(coverage.get(key)).get("count")),
                               "httpStatus": _number(_record(coverage.get(key)).get("httpStatus"))}
                         for key in ("debt", "interestRates")},
            "debtUrl": _safe_url(raw.get("debtUrl")), "ratesUrl": _safe_url(raw.get("ratesUrl")),
            "note": "存量债务平均付息率，不是当前市场收益率曲线；债务水平本身不是交易信号。",
            "signals": _signals(raw.get("signals"))}


def _news_coverage(value: Any, now: datetime) -> dict[str, Any] | None:
    raw = _record(value)
    if not raw:
        return None
    items = []
    for item in _records(raw.get("items"), limit=40):
        name = _text(item.get("source"), limit=80)
        if not name:
            continue
        status = item.get("status") if item.get("status") in {"ok", "partial", "error"} else "unknown"
        count = _number(item.get("count"))
        as_of = _timestamp(item.get("asOf"))
        data_as_of = _timestamp(item.get("dataAsOf"))
        cached = item.get("cached") is True
        available = _number(item.get("availableCount"))
        error_code = _text(item.get("errorCode"), limit=80)
        http_status = _number(item.get("httpStatus"))
        items.append({"source": name, "status": status,
                      "count": int(count) if status in {"ok", "partial"} and count is not None and count >= 0 else None,
                      "reason": _text(item.get("reason")), "asOf": as_of,
                      "sourceUrl": _safe_url(item.get("url")),
                      "errorCode": error_code if status == "error" and error_code in {
                          "RSS_TIMEOUT", "RSS_DNS_ERROR", "RSS_TLS_ERROR", "RSS_CONNECTION_REFUSED",
                          "RSS_NETWORK_ERROR", "RSS_HTTP_ERROR", "RSS_INVALID_FEED"} else None,
                      "httpStatus": int(http_status) if status == "error" and http_status is not None
                          and 100 <= http_status <= 599 and http_status % 1 == 0 else None,
                      "freshness": _freshness(as_of, now=now),
                      "cached": cached, "dataAsOf": data_as_of,
                      "availableCount": max(0, int(available)) if available is not None else None,
                      "dataFreshness": _freshness(data_as_of, now=now, degraded=cached)})
    requested = max(len(items), int(_number(_record(raw.get("coverage")).get("requested")) or 0))
    counts = {status: sum(item["status"] == status for item in items) for status in ("ok", "partial", "error", "unknown")}
    counts["unknown"] += requested - len(items)
    status = ("unknown" if requested == 0 or counts["unknown"] == requested else
              "ok" if counts["ok"] == requested else
              "partial" if counts["ok"] + counts["partial"] else "error")
    cached_sources = sum(item["cached"] for item in items)
    cache = _record(raw.get("cache"))
    if cached_sources or (cache.get("status") == "error" and status == "ok"):
        status = "partial"
    as_of = _timestamp(raw.get("asOf"))
    return {"status": status, "asOf": as_of, "freshness": _freshness(as_of, now=now, degraded=cached_sources > 0),
            "cachedSources": cached_sources,
            "mode": "cache" if raw.get("mode") == "cache" else "refresh",
            "cache": {"status": _text(cache.get("status")), "reason": _text(cache.get("reason"))},
            "coverage": {"requested": requested, "succeeded": counts["ok"], "partial": counts["partial"],
                         "failed": counts["error"], "unknown": counts["unknown"]},
            "displayedCount": _number(raw.get("displayedCount")),
            "eligibleCount": _number(raw.get("eligibleCount")), "limit": _number(raw.get("limit")),
            "selection": _text(raw.get("selection"), limit=80) or "regional-reserve-30d-v1",
            "items": items}


def _monitoring_areas(root: dict[str, Any], now: datetime, *, radiation: bool) -> list[dict[str, Any]]:
    expected_basis = "query-radius-center" if radiation else "query-bounds-center"
    result = []
    for item in _records(root.get("nuke" if radiation else "air"), limit=40):
        lat, lon = _number(item.get("lat")), _number(item.get("lon"))
        located = item.get("geoBasis") == expected_basis and lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180
        observed_at = _timestamp(item.get("observedAt"))
        cached = not radiation and _record(root.get("airMeta")).get("fallback") is True
        result.append({
            "id": _text(item.get("key")), "name": _text(item.get("site" if radiation else "region")),
            "latitude": lat if located else None, "longitude": lon if located else None,
            "geoBasis": expected_basis if located else "unlocated",
            "status": item.get("status") if item.get("status") in {"ok", "partial", "error"} else "unknown",
            "observedAt": observed_at, "freshness": _freshness(observed_at, now=now, degraded=cached),
            "cached": cached,
            **({"assessment": "unassessed", "radiusKm": _number(item.get("radiusKm")),
                "windowStart": _timestamp(item.get("windowStart")), "windowEnd": _timestamp(item.get("windowEnd")),
                "sampleLimit": _number(item.get("sampleLimit")),
                "recentReadings": _number(item.get("n")), "sampleReadings": _number(item.get("sampleReadings")),
                "avgCPM": _number(item.get("cpm")) if item.get("deviceId") is not None else None,
                "deviceId": _text(item.get("deviceId")), "reason": _text(item.get("reason")),
                "measurements": [{"value": _number(m.get("value")), "unit": _text(m.get("unit")),
                                  "deviceId": _text(m.get("deviceId")), "observedAt": _timestamp(m.get("observedAt"))}
                                 for m in _records(item.get("measurements"), limit=10)]}
               if radiation else {"totalAircraft": _number(item.get("total")),
                                  "noCallsign": _number(item.get("noCallsign")),
                                  "highAltitude": _number(item.get("highAlt"))}),
        })
    return result


def _conflict_groups(value: Any) -> dict[str, dict[str, int | float | None]]:
    return {
        _text(key, limit=100): {field: _number(_record(row).get(field)) for field in ("count", "fatalities", "unknownFatalities")}
        for key, row in list(_record(value).items())[:80]
    }


def _ofac_observation(value: Any, now: datetime) -> dict[str, Any] | None:
    raw = _record(value)
    if not raw:
        return None
    sdn = _record(raw.get("sdnList"))
    status = raw.get("status") if raw.get("status") in {"ok", "partial", "error"} else "unknown"
    known = status in {"ok", "partial"} and sdn.get("dataAvailable") is True and sdn.get("countBasis") == "sdn-entries"

    def count(key):
        number = _number(sdn.get(key)) if known else None
        return int(number) if number is not None and number >= 0 and number % 1 == 0 else None

    actual, declared = count("entryCount"), count("recordCount")
    published = _observation_period(sdn.get("publishDate")) if known else None
    if published and published > now.date().isoformat():
        published = None
    complete = known and sdn.get("complete") is True and published is not None and actual is not None and actual == declared
    reason = _text(raw.get("reason"))
    if status in {"ok", "partial"} and not known:
        status, reason = "unknown", "名单缺少完整读取口径，数量待核验"
    elif status == "ok" and not complete:
        status, reason = "partial", "名单日期、数量或完整性待核验"
    checked = _timestamp(raw.get("collectedAt"))
    collected = checked if known else None
    return {"status": status, "reason": reason, "publishedDate": published,
            "entryCount": actual, "recordCount": declared, "complete": complete,
            "countBasis": "sdn-entries", "collectedAt": collected, "checkedAt": checked,
            "collectionFreshness": _freshness(collected, now=now),
            "sourceUrl": "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML",
            "note": "仅美国 OFAC SDN 名单观察，未覆盖非 SDN 名单；数量不是新增制裁，非合规筛查或风险评级。"}


def _who_observation(root: Mapping, now: datetime) -> dict[str, Any] | None:
    meta = _record(root.get("whoMeta"))
    if not meta or not any(meta.get(key) is not None for key in ("collectedAt", "window", "count")):
        return None
    status = meta.get("status") if meta.get("status") in {"ok", "partial", "error"} else "unknown"
    checked = _timestamp(meta.get("collectedAt"))
    raw_window = _record(meta.get("window"))
    window = {"start": _timestamp(raw_window.get("start")), "end": _timestamp(raw_window.get("end")), "days": _number(raw_window.get("days"))}
    numeric = _number(meta.get("count"))
    times = [datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None for value in (window["start"], window["end"], checked)]
    valid_window = all(times) and times[0] < times[1] <= times[2] <= now and window["days"] == 30 and (times[1] - times[0]).total_seconds() == 30 * 86400
    displayed = len(_records(root.get("who"), limit=10))
    known = (status in {"ok", "partial"} and valid_window and numeric is not None
        and displayed <= numeric <= 100 and numeric % 1 == 0)
    gaps = {_text(key, limit=80): _text(value, limit=240) for key, value in list(_record(meta.get("gaps")).items())[:12]}
    if status in {"ok", "partial"} and not known:
        status = "unknown"
        gaps["evidence"] = "公告数量、30日查询窗口或原采集回执未核验，不能判断窗口内没有公告。"
    elif status == "ok" and (gaps or numeric == 100):
        status = "partial"
        if numeric == 100:
            gaps["pagination"] = "达到查询上限，窗口内可能仍有后续公告。"
    collected = checked if known else None
    return {"status": status, "reportCount": int(numeric) if known else None, "window": window,
        "displayed": displayed, "queryLimit": 100, "sourceDisplayLimit": 15,
        "complete": status == "ok" and known and not gaps, "gaps": gaps,
        "collectedAt": collected, "checkedAt": checked, "freshness": _freshness(collected, now=now),
        "sourceUrl": "https://www.who.int/emergencies/disease-outbreak-news",
        "note": "仅 WHO DON 近30日查询内的公告样本，公告数不是感染人数，也不证明没有其他疫情；公告发布日期非疫情发生时间，完整查询也不代表全球疫情全覆盖。"}


def normalize_snapshot(
    payload: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _record(payload)
    if not root:
        raise ValueError("Crucix returned an invalid snapshot")
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    meta = _record(root.get("meta"))
    as_of = _timestamp(meta.get("timestamp"))

    source_items: list[dict[str, Any]] = []
    for item in _records(root.get("health"), limit=80):
        name = _text(item.get("n", item.get("name")), limit=80)
        if not name:
            continue
        status = item.get("status") if item.get("status") in {"ok", "error", "partial", "stale", "unknown"} else (
            "error"
            if item.get("err") is True
            else "stale" if item.get("stale") is True else "ok"
        )
        source_items.append({"source": name, "status": status,
                             **({"reason": _text(item["reason"])} if item.get("reason") else {})})
    source_items = list({item["source"]: item for item in source_items}.values())
    queried = max(int(_number(meta.get("sourcesQueried")) or 0), len(source_items))
    # Counts and detail must agree; absent legacy detail is unknown, not a successful source.
    counts = {status: sum(item["status"] == status for item in source_items)
              for status in ("ok", "error", "partial", "stale", "unknown")}
    counts["unknown"] += queried - len(source_items)

    who = _who_observation(root, clock)
    news: list[dict[str, Any]] = []
    seen_news: set[tuple[str, str, str]] = set()
    # The general ticker caps at 50 and can crowd out every official WHO bulletin.
    # Keep the already-collected native sample; do not request or invent more reports.
    who_news = [{"headline": item.get("title"), "timestamp": item.get("date"), "url": item.get("url"),
                 "source": "WHO", "type": "who"} for item in _records(root.get("who"), limit=10)]
    for item in who_news + _records(root.get("newsFeed"), limit=120):
        title = _text(item.get("headline", item.get("title")), limit=300)
        if not title:
            continue
        source = _text(item.get("source"), limit=100) or "Crucix"
        is_gdelt = item.get("type") == "gdelt" or source.upper() == "GDELT"
        # Legacy GDELT feed items used the sweep clock. Do not trust that as publication.
        published_at = None if is_gdelt else _timestamp(item.get("timestamp"))
        indexed_at = _timestamp(item.get("timestamp")) if is_gdelt and item.get("timestampBasis") == "indexed" else None
        url = _safe_url(item.get("url"))
        key = (url or title.casefold(), source.casefold(), published_at or "")
        if key in seen_news:
            continue
        seen_news.add(key)
        news.append(
            {
                "title": title,
                "source": source,
                "type": _text(item.get("type"), limit=40) or "news",
                "publishedAt": published_at,
                **({"collectedAt": _timestamp(item.get("collectedAt")),
                    "cached": item.get("cached") is True,
                    "sourceStatus": _text(item.get("sourceStatus")),
                    "collectionFreshness": _freshness(_timestamp(item.get("collectedAt")), now=clock,
                                                      degraded=item.get("cached") is True)}
                   if item.get("type") == "rss" and "collectedAt" in item else {}),
                **({"collectedAt": who.get("collectedAt") if who else None,
                    "collectionFreshness": who["freshness"] if who else _freshness(None, now=clock),
                    "sourceStatus": who["status"] if who else "unknown"}
                   if item.get("type") == "who" and source == "WHO" else {}),
                **({"indexedAt": indexed_at} if indexed_at else {}),
                "region": _text(item.get("region"), limit=80) or "Global",
                "urgent": item.get("urgent") is True,
                **({"url": url} if url else {}),
            }
        )

    treasury = _record(root.get("treasury"))
    gscpi = _record(root.get("gscpi"))
    energy = _record(root.get("energy"))
    metals = _record(root.get("metals"))
    macro = {
        "fred": _indicators(root.get("fred")),
        "bls": _indicators(root.get("bls"), monthly=True, now=clock),
        "treasury": _treasury_snapshot(treasury, clock),
        "gscpi": _supply_observation(gscpi, source_items, clock),
        "metals": {"observations": _metal_observations(metals, source_items, clock)} if metals else None,
        "energy": {
            "wti": _number(energy.get("wti")),
            "brent": _number(energy.get("brent")),
            "naturalGas": _number(energy.get("natgas")),
            "crudeStocks": _number(energy.get("crudeStocks")),
            "wtiRecent": _series(energy.get("wtiRecent")),
            "signals": _signals(energy.get("signals")),
            "observations": _energy_observations(energy, source_items, clock),
            "note": "采集时间不等于数据时间；按 observations 分别识别现货、期货和库存，不跨口径比较。",
        },
    }

    acled = _record(root.get("acled"))
    acled_known = acled.get("status") in {"ok", "partial"} and acled.get("basis") == "bounded-event-sample"
    acled_events: list[dict[str, Any]] = []
    for item in _records(acled.get("deadliestEvents") if acled_known else [], limit=20):
        acled_events.append(
            {
                "id": _text(item.get("id"), limit=100),
                "date": _timestamp(item.get("date")),
                "type": _text(item.get("type"), limit=100),
                "country": _text(item.get("country"), limit=100),
                "location": _text(item.get("location"), limit=160),
                "fatalities": _number(item.get("fatalities")),
                "latitude": _number(item.get("lat")),
                "longitude": _number(item.get("lon")),
            }
        )
    gdelt = _record(root.get("gdelt"))
    gdelt_article_count = _number(gdelt.get("totalArticles"))
    gdelt_titles: list[str] = []
    top_titles = gdelt.get("topTitles")
    if isinstance(top_titles, list):
        gdelt_titles = [
            title
            for item in top_titles[:20]
            if (title := _text(item, limit=300))
        ]
    gdelt_points: list[dict[str, Any]] = []
    for item in _records(gdelt.get("geoPoints"), limit=40):
        latitude = _number(item.get("lat"))
        longitude = _number(item.get("lon"))
        if latitude is None or longitude is None:
            continue
        gdelt_points.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "title": _text(item.get("name"), limit=200) or "GDELT event",
                "count": _number(item.get("count")),
            }
        )

    noaa = _record(root.get("noaa"))
    weather_alerts = []
    for item in _records(noaa.get("alerts"), limit=50):
        weather_alerts.append(
            {
                "id": _text(item.get("id"), limit=300),
                "url": _safe_url(item.get("url")),
                "event": _text(item.get("event"), limit=120),
                "severity": _text(item.get("severity"), limit=40),
                "headline": _text(item.get("headline"), limit=300),
                "latitude": _number(item.get("lat")),
                "longitude": _number(item.get("lon")),
                "geoBasis": _text(item.get("geoBasis"), limit=40),
                "areas": _text(item.get("areas"), limit=600),
                "sent": _timestamp(item.get("sent")),
                "effective": _timestamp(item.get("effective")),
                "onset": _timestamp(item.get("onset")),
                "expires": _timestamp(item.get("expires")),
            }
        )

    epa = _record(root.get("epa"))
    radiation_stations = []
    for item in _records(epa.get("stations"), limit=30):
        radiation_stations.append(
            {
                "location": _text(item.get("location"), limit=120),
                "state": _text(item.get("state"), limit=80),
                "latitude": _number(item.get("lat")),
                "longitude": _number(item.get("lon")),
                "analyte": _text(item.get("analyte"), limit=80),
                "result": _number(item.get("result")),
                "unit": _text(item.get("unit"), limit=40),
            }
        )

    space = _record(root.get("space"))
    launches = []
    for item in _records(space.get("recentLaunches"), limit=20):
        launches.append(
            {
                "name": _text(item.get("name"), limit=160),
                "country": _text(item.get("country"), limit=80),
                "epoch": _timestamp(item.get("epoch")),
                "apogee": _number(item.get("apogee")),
                "perigee": _number(item.get("perigee")),
                "type": _text(item.get("type"), limit=80),
            }
        )

    defense_contracts = []
    for item in _records(root.get("defense"), limit=20):
        defense_contracts.append(
            {
                "recipient": _text(item.get("recipient"), limit=120),
                "amount": _number(item.get("amount")),
                "description": _text(item.get("desc", item.get("description")), limit=300),
            }
        )

    global_intel = {
        "who": who,
        "airRegions": _monitoring_areas(root, clock, radiation=False),
        "radiationAreas": _monitoring_areas(root, clock, radiation=True),
        "acled": {
            "status": _text(acled.get("status")) or "unknown",
            "basis": "bounded-event-sample" if acled.get("basis") == "bounded-event-sample" else None,
            "collectedAt": _timestamp(acled.get("collectedAt")),
            "period": {key: _text(_record(acled.get("period")).get(key), limit=10) or None for key in ("start", "end")},
            "coverage": {**_number_map(acled.get("coverage")), "truncated": _record(acled.get("coverage")).get("truncated") is True},
            "errorCode": _text(acled.get("errorCode")) or None,
            "httpStatus": _number(acled.get("httpStatus")),
            "totalEvents": _number(acled.get("totalEvents")) if acled_known else None,
            "totalFatalities": _number(acled.get("totalFatalities")) if acled_known else None,
            "byRegion": _conflict_groups(acled.get("byRegion")) if acled_known else {},
            "byType": _conflict_groups(acled.get("byType")) if acled_known else {},
            "deadliestEvents": acled_events,
        },
        "gdelt": {
            "totalArticles": int(gdelt_article_count) if gdelt_article_count is not None else None,
            "coverage": _number_map(gdelt.get("coverage")),
            "gaps": {key: _text(value) for key, value in _record(gdelt.get("gaps")).items() if key in {"articles", "geo"}},
            "topTitles": gdelt_titles,
            "geoPoints": gdelt_points,
        },
        "ofac": _ofac_observation(root.get("ofac"), clock),
        "weatherAlerts": weather_alerts,
        "weatherCoverage": {
            "status": _text(noaa.get("status")) or "unknown",
            "totalAlerts": _number(noaa.get("totalAlerts")) if noaa.get("status") in {"ok", "partial"} else None,
            "collectedAt": _timestamp(noaa.get("collectedAt")),
            "updatedAt": _timestamp(noaa.get("updatedAt")),
            "freshness": _freshness(_timestamp(noaa.get("collectedAt")), now=clock),
            "region": "US/NWS",
            "displayed": len(weather_alerts),
            "complete": _record(noaa.get("coverage")).get("complete") is True,
            "errorCode": _text(noaa.get("errorCode")) or None,
            "httpStatus": _number(noaa.get("httpStatus")),
        } if noaa else None,
        "radiationStations": radiation_stations,
        "space": {
            "militarySatellites": int(_number(space.get("militarySats")) or 0),
            "constellations": _number_map(space.get("constellations")),
            "recentLaunches": launches,
            "signals": _signals(space.get("signals")),
        },
        "defenseContracts": defense_contracts,
    }

    return {
        "contract": SNAPSHOT_CONTRACT,
        "asOf": as_of,
        "freshness": _freshness(as_of, now=clock),
        "sourceHealth": {
            "queried": queried,
            "ok": counts["ok"],
            "failed": counts["error"],
            "partial": counts["partial"],
            "stale": counts["stale"],
            "unknown": counts["unknown"],
            "items": source_items,
        },
        "news": news[:80],
        "newsCoverage": _news_coverage(root.get("newsMeta"), clock),
        "macro": macro,
        "comparison": _comparison(root, clock),
        "global": global_intel,
        "provenance": {
            "project": "Crucix",
            "license": "AGPL-3.0-only",
            "mode": "external-runtime",
        },
    }


def normalize_health(
    payload: Any,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _record(payload)
    if not root:
        raise ValueError("Crucix returned an invalid health response")
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    last_sweep = _timestamp(root.get("lastSweep"))
    refresh_minutes = int(_number(root.get("refreshIntervalMinutes")) or 60)
    freshness = _freshness(
        last_sweep,
        now=clock,
        stale_after_seconds=max(300, refresh_minutes * 120),
    )
    ok = int(_number(root.get("sourcesOk")) or 0)
    failed = int(_number(root.get("sourcesFailed")) or 0)
    partial = int(_number(root.get("sourcesPartial")) or 0)
    stale = int(_number(root.get("sourcesStale")) or 0)
    unknown = int(_number(root.get("sourcesUnknown")) or 0)
    queried = int(_number(root.get("sourcesQueried")) or (ok + failed + partial + stale + unknown))
    in_progress = root.get("sweepInProgress") is True
    if not last_sweep and in_progress:
        status = "starting"
    elif root.get("status") != "ok" or queried == 0 or ok != queried or freshness["status"] != "fresh":
        status = "degraded"
    else:
        status = "ok"
    return {
        "contract": HEALTH_CONTRACT,
        "status": status,
        "service": "crucix",
        "asOf": last_sweep,
        "freshness": freshness,
        "sourceHealth": {"queried": queried, "ok": ok, "failed": failed, "partial": partial, "stale": stale, "unknown": unknown},
        "sweep": {
            "inProgress": in_progress,
            "startedAt": _timestamp(root.get("sweepStartedAt")),
            "nextAt": _timestamp(root.get("nextSweep")),
            "refreshIntervalMinutes": refresh_minutes,
        },
    }


def adapt_crucix_response(capability_id: str, payload: Any) -> dict[str, Any]:
    if capability_id == "crucix.snapshot":
        return normalize_snapshot(payload)
    if capability_id == "crucix.health":
        return normalize_health(payload)
    raise ValueError("unknown Crucix capability")
