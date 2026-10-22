import calendar
import html
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


def _freshness(
    as_of: str | None,
    *,
    now: datetime,
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
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
        "status": "stale" if age_seconds > stale_after_seconds else "fresh",
        "ageSeconds": age_seconds,
        "staleAfterSeconds": stale_after_seconds,
    }


def _indicators(value: Any) -> list[dict[str, Any]]:
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
            "source": provenance,
            "note": _text(item.get("note")) or "旧快照未保留来源、报价类型与数据时间；不能视为 EIA 现货或实时价格。",
            "freshness": _observation_freshness(value, period, observed_at, frequency, now, degraded=degraded),
        })
    return result


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

    news: list[dict[str, Any]] = []
    seen_news: set[tuple[str, str, str]] = set()
    for item in _records(root.get("newsFeed"), limit=120):
        title = _text(item.get("headline", item.get("title")), limit=300)
        if not title:
            continue
        source = _text(item.get("source"), limit=100) or "Crucix"
        is_gdelt = item.get("type") == "gdelt" or source.upper() == "GDELT"
        # Legacy GDELT feed items used the sweep clock. Do not trust that as publication.
        published_at = None if is_gdelt else _timestamp(item.get("timestamp"))
        indexed_at = _timestamp(item.get("timestamp")) if is_gdelt and item.get("timestampBasis") == "indexed" else None
        key = (title.casefold(), source.casefold(), published_at or "")
        if key in seen_news:
            continue
        seen_news.add(key)
        url = _safe_url(item.get("url"))
        news.append(
            {
                "title": title,
                "source": source,
                "type": _text(item.get("type"), limit=40) or "news",
                "publishedAt": published_at,
                **({"indexedAt": indexed_at} if indexed_at else {}),
                "region": _text(item.get("region"), limit=80) or "Global",
                "urgent": item.get("urgent") is True,
                **({"url": url} if url else {}),
            }
        )

    treasury = _record(root.get("treasury"))
    gscpi = _record(root.get("gscpi"))
    energy = _record(root.get("energy"))
    gscpi_period = _observation_period(gscpi.get("date"), monthly=True)
    gscpi_value = _number(gscpi.get("value"))
    macro = {
        "fred": _indicators(root.get("fred")),
        "bls": _indicators(root.get("bls")),
        "treasury": {
            "totalDebt": _text(treasury.get("totalDebt"), limit=80),
            "signals": _signals(treasury.get("signals")),
        },
        "gscpi": {
            "value": gscpi_value,
            "date": gscpi_period, "period": gscpi_period, "dateBasis": "period", "unit": "标准差",
            "source": {"id": "GSCPI", "label": "纽约联储", "seriesId": "GSCPI",
                       "url": "https://www.newyorkfed.org/research/policy/gscpi"},
            "freshness": _observation_freshness(gscpi_value, gscpi_period, None, "monthly", clock,
                degraded=any(row["source"] == "GSCPI" and row["status"] != "ok" for row in source_items)),
            "interpretation": _text(gscpi.get("interpretation"), limit=240),
        } if gscpi else None,
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
    acled_events: list[dict[str, Any]] = []
    for item in _records(acled.get("deadliestEvents"), limit=20):
        acled_events.append(
            {
                "date": _timestamp(item.get("date")),
                "type": _text(item.get("type"), limit=100),
                "country": _text(item.get("country"), limit=100),
                "location": _text(item.get("location"), limit=160),
                "fatalities": _number(item.get("fatalities")) or 0,
                "latitude": _number(item.get("lat")),
                "longitude": _number(item.get("lon")),
            }
        )
    gdelt = _record(root.get("gdelt"))
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
                "count": _number(item.get("count")) or 1,
            }
        )

    noaa = _record(root.get("noaa"))
    weather_alerts = []
    for item in _records(noaa.get("alerts"), limit=30):
        weather_alerts.append(
            {
                "event": _text(item.get("event"), limit=120),
                "severity": _text(item.get("severity"), limit=40),
                "headline": _text(item.get("headline"), limit=300),
                "latitude": _number(item.get("lat")),
                "longitude": _number(item.get("lon")),
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
        "acled": {
            "totalEvents": int(_number(acled.get("totalEvents")) or 0),
            "totalFatalities": int(_number(acled.get("totalFatalities")) or 0),
            "byRegion": _number_map(acled.get("byRegion")),
            "byType": _number_map(acled.get("byType")),
            "deadliestEvents": acled_events,
        },
        "gdelt": {
            "totalArticles": int(_number(gdelt.get("totalArticles")) or 0),
            "topTitles": gdelt_titles,
            "geoPoints": gdelt_points,
        },
        "weatherAlerts": weather_alerts,
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
        "macro": macro,
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
