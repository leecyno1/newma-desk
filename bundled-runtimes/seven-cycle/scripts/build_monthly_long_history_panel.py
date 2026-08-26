"""
Build a long-history *monthly* panel (DatetimeIndex, month-end) for 1900–2024.

Sources
- OECD via OpenBB local API (monthly): CPI YoY, unemployment, rates, share/house price indices, CLI (where available)
- Robert Shiller (public, monthly): US market/cpi/yields (1871–latest in file)

Outputs
- data/indicator_panel_monthly_long_history.parquet
- output/monthly_long_history_summary.md
"""

from __future__ import annotations

from pathlib import Path
import json
import re
import time

import pandas as pd
import requests


OPENBB_BASE_URL = "http://127.0.0.1:6900"
SHILLER_XLS_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"


# Keep OECD requests small to avoid OECD API rate limits; US is covered well by Shiller.
OECD_COUNTRIES = ["united_kingdom"]


def _slug(s: str, max_len: int = 80) -> str:
    s = str(s).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = s.strip("_") or "NA"
    return s[:max_len].rstrip("_")


def _download(url: str, dest: Path, *, timeout: int = 120) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _openbb_cache_path(endpoint: str, params: dict[str, object]) -> Path:
    parts = [_slug(endpoint)]
    for k in sorted(params.keys()):
        v = params[k]
        if v is None:
            continue
        parts.append(_slug(f"{k}={v}"))
    return Path("data/raw/openbb_cache") / ("__".join(parts)[:200] + ".json")


def _openbb_get(path: str, params: dict[str, object], *, timeout: int = 120) -> list[dict]:
    cache = _openbb_cache_path(path.strip("/").replace("/", "_"), params)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 10:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return list(payload.get("results", []) or [])

    url = f"{OPENBB_BASE_URL}{path}"
    # OECD endpoints may transiently fail with an embedded "429" in error messages; retry briefly.
    for sleep_s in [0, 2]:
        if sleep_s:
            time.sleep(sleep_s)
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 204:
            return []
        if r.status_code >= 400:
            if "429" in (r.text or ""):
                continue
            return []
        break
    else:
        return []
    payload = r.json()
    cache.write_text(json.dumps(payload), encoding="utf-8")
    return list(payload.get("results", []) or [])


def _fetch_oecd_monthly(endpoint: str, *, country: str, extra: dict[str, object] | None = None) -> pd.Series:
    params: dict[str, object] = {
        "provider": "oecd",
        "country": country,
        "frequency": "monthly",
        "start_date": "1960-01-01",
        "end_date": "2024-12-31",
    }
    if extra:
        params.update(extra)
    data = _openbb_get(f"/api/v1/economy/{endpoint}", params, timeout=120)
    if not data:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(data)
    if "date" not in df.columns or "value" not in df.columns:
        return pd.Series(dtype="float64")
    dt = pd.to_datetime(df["date"], errors="coerce").dt.to_period("M").dt.to_timestamp("M")
    s = pd.to_numeric(df["value"], errors="coerce")
    out = pd.Series(s.values, index=pd.DatetimeIndex(dt)).sort_index()
    out = out[~out.index.isna()].groupby(level=0).last().sort_index()
    return out


def _load_shiller_monthly(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Data", header=7)
    if "Date" not in df.columns:
        raise RuntimeError("Shiller dataset: missing Date column")
    s = df["Date"].astype(str).str.strip()
    years = pd.to_numeric(s.str.split(".").str[0], errors="coerce")
    months = pd.to_numeric(s.str.split(".").str[1], errors="coerce")
    dt = pd.to_datetime(pd.DataFrame({"year": years, "month": months, "day": 1}), errors="coerce")
    dt = dt.dt.to_period("M").dt.to_timestamp("M")
    df = df.copy()
    df["date"] = pd.DatetimeIndex(dt)
    df = df.dropna(subset=["date"]).set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def _summary(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        s = df[c]
        non = int(s.notna().sum())
        total = int(len(s))
        start = s.dropna().index.min() if non else None
        end = s.dropna().index.max() if non else None
        rows.append(
            {
                "column": c,
                "non_null": non,
                "total_months": total,
                "start": start,
                "end": end,
                "missing_pct": float((1 - non / total) * 100) if total else 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["missing_pct", "column"]).reset_index(drop=True)


def main(
    *,
    start: str = "1900-01-31",
    end: str = "2024-12-31",
    out_path: Path = Path("data/indicator_panel_monthly_long_history.parquet"),
    summary_path: Path = Path("output/monthly_long_history_summary.md"),
) -> None:
    idx = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq="ME")
    panel: dict[str, pd.Series] = {}

    # OECD series (monthly)
    for c in OECD_COUNTRIES:
        tag = c.upper()
        cpi = _fetch_oecd_monthly("cpi", country=c, extra={"transform": "yoy", "expenditure": "total"}) * 100.0
        un = _fetch_oecd_monthly("unemployment", country=c) * 100.0
        ir_l = _fetch_oecd_monthly("interest_rates", country=c, extra={"duration": "long"}) * 100.0
        ir_s = _fetch_oecd_monthly("interest_rates", country=c, extra={"duration": "short"}) * 100.0
        spx = _fetch_oecd_monthly("share_price_index", country=c)
        hpx = _fetch_oecd_monthly("house_price_index", country=c)
        cli = _fetch_oecd_monthly("composite_leading_indicator", country=c)

        if not cpi.dropna().empty:
            panel[f"{tag}_OECD_CPI_YOY_PCT_M"] = cpi
        if not un.dropna().empty:
            panel[f"{tag}_OECD_UNEMPLOYMENT_PCT_M"] = un
        if not ir_l.dropna().empty:
            panel[f"{tag}_OECD_IR_LONG_PCT_M"] = ir_l
        if not ir_s.dropna().empty:
            panel[f"{tag}_OECD_IR_SHORT_PCT_M"] = ir_s
        if not spx.dropna().empty:
            panel[f"{tag}_OECD_SHARE_PRICE_INDEX_M"] = spx
        if not hpx.dropna().empty:
            panel[f"{tag}_OECD_HOUSE_PRICE_INDEX_M"] = hpx
        if not cli.dropna().empty:
            panel[f"{tag}_OECD_CLI_INDEX_M"] = cli

    # Euro area special keys
    ea_cpi = _fetch_oecd_monthly("cpi", country="euro_area_20", extra={"transform": "yoy", "expenditure": "total"}) * 100.0
    ea_un = _fetch_oecd_monthly("unemployment", country="euro_area20") * 100.0
    ea_ir_l = _fetch_oecd_monthly("interest_rates", country="euro_area19", extra={"duration": "long"}) * 100.0
    ea_ir_s = _fetch_oecd_monthly("interest_rates", country="euro_area19", extra={"duration": "short"}) * 100.0
    ea_spx = _fetch_oecd_monthly("share_price_index", country="euro_area_19")
    ea_hpx = _fetch_oecd_monthly("house_price_index", country="euro_area_20")
    if not ea_cpi.dropna().empty:
        panel["EA_OECD_CPI_YOY_PCT_M"] = ea_cpi
    if not ea_un.dropna().empty:
        panel["EA_OECD_UNEMPLOYMENT_PCT_M"] = ea_un
    if not ea_ir_l.dropna().empty:
        panel["EA_OECD_IR_LONG_PCT_M"] = ea_ir_l
    if not ea_ir_s.dropna().empty:
        panel["EA_OECD_IR_SHORT_PCT_M"] = ea_ir_s
    if not ea_spx.dropna().empty:
        panel["EA_OECD_SHARE_PRICE_INDEX_M"] = ea_spx
    if not ea_hpx.dropna().empty:
        panel["EA_OECD_HOUSE_PRICE_INDEX_M"] = ea_hpx

    # Shiller monthly (US)
    shiller_path = _download(SHILLER_XLS_URL, Path("data/raw/shiller_ie_data.xls"))
    try:
        sh = _load_shiller_monthly(shiller_path)
    except Exception:
        sh = pd.DataFrame()
    if not sh.empty:
        for out_name, src in [
            ("US_SHILLER_SP_PRICE_M", "P"),
            ("US_SHILLER_SP_DIVIDEND_M", "D"),
            ("US_SHILLER_SP_EARNINGS_M", "E"),
            ("US_SHILLER_CPI_M", "CPI"),
            ("US_SHILLER_CAPE_M", "CAPE"),
            ("US_SHILLER_GS10_YIELD_PCT_M", "Rate GS10"),
        ]:
            s = pd.to_numeric(sh.get(src), errors="coerce")
            if s is None or s.dropna().empty:
                continue
            panel[out_name] = s

    # Align to requested index (month-end)
    df = pd.DataFrame(index=idx)
    for k, s in panel.items():
        s = s[~s.index.duplicated(keep="last")]
        df[k] = s.reindex(idx)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)

    summ = _summary(df)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Monthly long-history panel",
        "",
        f"- Output: `{out_path}`",
        f"- Window: {start} ~ {end} (month-end)",
        f"- Shape: {df.shape[0]} months × {df.shape[1]} columns",
        "",
        "## Coverage summary",
        "",
        summ.to_markdown(index=False),
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
