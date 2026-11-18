"""Public policy-rate observations; historical references never fill current gaps."""

import asyncio
import csv
import io
import math
from datetime import date, datetime, timedelta, timezone

from ..fetcher import Fetcher
from ..source_time import source_cache_timing


# ---------------------------------------------------------------------------
# FRED series IDs for central bank rates
# ---------------------------------------------------------------------------

_RATE_SERIES: dict[str, dict] = {
    "fed_funds": {
        "series_id": "DFEDTARU",
        "bank": "Federal Reserve",
        "country": "USA",
        "currency": "USD",
        "label": "Fed target range upper bound / 目标区间上限",
        "source": "fred", "frequency": "daily-7-days", "rate_type": "target-upper-bound",
    },
    "ecb_deposit": {
        "series_id": "ECBDFR",
        "bank": "European Central Bank",
        "country": "EUR",
        "currency": "EUR",
        "label": "ECB Deposit Facility Rate",
        "source": "fred", "frequency": "daily-7-days", "rate_type": "deposit-facility",
    },
    "boe_bank_rate": {
        "series_id": "IUDBEDR",
        "bank": "Bank of England",
        "country": "GBR",
        "currency": "GBP",
        "label": "BoE Official Bank Rate",
        "source": "boe", "frequency": "daily-business-days", "rate_type": "official-bank-rate",
    },
}

_FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
_BOE_CSV_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"

# ---------------------------------------------------------------------------
# Historical manual references, NOT verified current policy settings.
# ---------------------------------------------------------------------------

_HISTORICAL_RATES: list[dict] = [
    {"bank": "Bank of Japan", "country": "JPN", "currency": "JPY",
     "label": "BoJ Policy Rate", "rate": 0.50, "as_of": "2025-01-24",
     "notes": "Short-term policy rate target"},
    {"bank": "People's Bank of China", "country": "CHN", "currency": "CNY",
     "label": "PBoC LPR 1Y", "rate": 3.10, "as_of": "2025-01-20",
     "notes": "1-year Loan Prime Rate"},
    {"bank": "Reserve Bank of India", "country": "IND", "currency": "INR",
     "label": "RBI Repo Rate", "rate": 6.50, "as_of": "2025-02-07",
     "notes": "Policy repo rate"},
    {"bank": "Reserve Bank of Australia", "country": "AUS", "currency": "AUD",
     "label": "RBA Cash Rate", "rate": 4.35, "as_of": "2024-11-05",
     "notes": "Cash rate target"},
    {"bank": "Bank of Canada", "country": "CAN", "currency": "CAD",
     "label": "BoC Overnight Rate", "rate": 3.25, "as_of": "2024-12-11",
     "notes": "Target for the overnight rate"},
    {"bank": "Swiss National Bank", "country": "CHE", "currency": "CHF",
     "label": "SNB Policy Rate", "rate": 0.50, "as_of": "2024-12-12",
     "notes": "SNB policy rate"},
    {"bank": "Central Bank of Brazil", "country": "BRA", "currency": "BRL",
     "label": "BCB SELIC", "rate": 13.25, "as_of": "2025-01-29",
     "notes": "SELIC target rate"},
    {"bank": "Bank of Korea", "country": "KOR", "currency": "KRW",
     "label": "BoK Base Rate", "rate": 3.00, "as_of": "2025-01-16",
     "notes": "Base rate"},
    {"bank": "Central Bank of Turkey", "country": "TUR", "currency": "TRY",
     "label": "CBRT Policy Rate", "rate": 45.00, "as_of": "2025-01-23",
     "notes": "1-week repo rate"},
    {"bank": "South African Reserve Bank", "country": "ZAF", "currency": "ZAR",
     "label": "SARB Repo Rate", "rate": 7.75, "as_of": "2024-11-21",
     "notes": "Repurchase rate"},
    {"bank": "Banco de México", "country": "MEX", "currency": "MXN",
     "label": "Banxico Target Rate", "rate": 10.00, "as_of": "2025-02-06",
     "notes": "Overnight interbank rate target"},
    {"bank": "Bank Indonesia", "country": "IDN", "currency": "IDR",
     "label": "BI Rate", "rate": 5.75, "as_of": "2025-01-15",
     "notes": "BI-Rate"},
    {"bank": "Federal Reserve", "country": "USA", "currency": "USD",
     "label": "Fed target range upper bound", "rate": 4.50, "as_of": "2025-01-29"},
    {"bank": "European Central Bank", "country": "EUR", "currency": "EUR",
     "label": "ECB Deposit Facility Rate", "rate": 2.75, "as_of": "2025-01-30"},
    {"bank": "Bank of England", "country": "GBR", "currency": "GBP",
     "label": "BoE Official Bank Rate", "rate": 4.50, "as_of": "2025-02-06"},
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _latest_observation(text: str, series_id: str, today: date) -> tuple[float | None, str | None]:
    """Exact series/date columns only; a missing newest value stays missing."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if series_id not in (reader.fieldnames or []):
        return None, None
    rows = []
    for row in reader:
        raw = row.get("observation_date", row.get("DATE", "")) or ""
        observed = None
        for pattern in ("%Y-%m-%d", "%d %b %Y"):
            try:
                observed = datetime.strptime(raw.strip(), pattern).date()
                break
            except ValueError:
                continue
        if observed is None or observed > today or observed < today - timedelta(days=45):
            continue
        try:
            value = float(row.get(series_id) or "nan")
            value = value if math.isfinite(value) else None
        except ValueError:
            value = None
        rows.append((observed, value))
    if not rows:
        return None, None
    latest = max(row[0] for row in rows)
    values = {value for observed, value in rows if observed == latest}
    return (next(iter(values)) if len(values) == 1 else None), latest.isoformat()


async def _fetch_rate(fetcher: Fetcher, meta: dict, today: date) -> dict:
    series_id = meta["series_id"]
    start = today - timedelta(days=45)
    boe = meta["source"] == "boe"
    params = {"csv.x": "yes", "Datefrom": start.strftime("%d/%b/%Y"), "Dateto": today.strftime("%d/%b/%Y"),
              "SeriesCodes": series_id, "CSVF": "TN", "UsingCodes": "Y", "VPD": "Y", "VFD": "N"} if boe else {
        "id": series_id, "cosd": start.isoformat(), "coed": today.isoformat(),
    }
    # New namespace: legacy API/curated cache entries must not appear as live evidence.
    key = f"central_banks:public-v1:{series_id}"
    text = await fetcher.get_text(_BOE_CSV_URL if boe else _FRED_CSV_URL, source=meta["source"],
                                  cache_key=key, cache_ttl=3600, params=params, timeout=10)
    timing = source_cache_timing(fetcher.cache, key)
    value, observed = _latest_observation(text or "", series_id, today)
    stale = timing["freshness"] != "fresh" or (observed is not None and (today - date.fromisoformat(observed)).days > 7)
    status = "unavailable" if value is None else "stale" if stale else "available"
    return {**meta, "rate": value, "as_of": observed, "unit": "percent", "status": status,
            "source_url": "https://www.bankofengland.co.uk/boeapps/database/Bank-Rate.asp" if boe else f"https://fred.stlouisfed.org/series/{series_id}",
            **timing, "observation_freshness": status,
            "reason": "来源响应无有效最新观测，未用历史参考填补" if value is None else
                      "保留原观测；缓存过期或观测超过7日，现行值待核验" if stale else
                      "已读取日频政策利率观测；观测日不代表调息日"}


async def fetch_central_bank_rates(fetcher: Fetcher) -> dict:
    """Track 15 banks; fetch 3 official series without keys. Unconnected values stay null."""
    today = datetime.now(timezone.utc).date()
    results = await asyncio.gather(*[_fetch_rate(fetcher, meta, today) for meta in _RATE_SERIES.values()])
    by_bank = {row["bank"]: row for row in results}
    rates = []
    for reference in _HISTORICAL_RATES:
        row = by_bank.get(reference["bank"], {
            **{key: reference[key] for key in ("bank", "country", "currency", "label")},
            "rate": None, "as_of": None, "source": "unavailable", "status": "reference-only",
            "reason": "尚未接入现行来源；历史参考不代表当前政策", "unit": "percent",
        })
        rates.append({**row, "reference": {**reference, "source": "curated"}})
    available = sum(row["status"] == "available" for row in results)
    stale = sum(row["status"] == "stale" for row in results)
    return {"rates": rates, "count": len(rates), "source": "multi", "timestamp": _utc_now_iso(),
            "status": "partial", "fred_available": any(row["source"] == "fred" and row["status"] == "available" for row in results),
            "coverage": {"tracked": len(rates), "queried": len(results), "available": available,
                         "stale": stale, "failed": len(results) - available - stale, "reference_only": len(rates) - len(results)},
            "sources": results, "caveat": "观测日不等于调息日；政策工具不同，不按数值高低推断鹰鸽。历史参考不可用于当前利差或交易信号。"}
