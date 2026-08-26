"""
Build a *long-history* annual panel (year index) for long-cycle research.

Why a year-index panel?
- pandas.Timestamp cannot represent dates earlier than 1677 (nanosecond resolution limit).
- Long-run datasets often start in 1700/1800/1900, so we store the index as an **integer year**.

Coverage target (relaxed requirement):
- Default: 1800–2024 (configurable)

Data sources (multi-source):
- Bank of England: "A millennium of macroeconomic data for the UK" (annual, up to 2016)
- OECD via OpenBB local API: macro/asset indicators to 2024; also used to extend some BoE series past 2016
- World Bank API: used to extend selected level/index series to the latest available year (typically 2024)
- Robert Shiller (public): long-run US stock/bond/CPI monthly dataset (aggregated to annual)
- Maddison Project Database (public): multi-country GDP per capita + population (to 2018), extended to 2024 by World Bank growth splicing

Outputs
- data/indicator_panel_annual_long_history_year.parquet
- output/annual_long_history_summary.md
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import time
import re

import pandas as pd
import requests


BOE_XLSX_URL = (
    "https://www.bankofengland.co.uk/-/media/boe/files/statistics/research-datasets/"
    "a-millennium-of-macroeconomic-data-for-the-uk.xlsx"
)
SHILLER_XLS_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
MADDISON_MPD2020_XLSX_URL = "https://www.rug.nl/ggdc/historicaldevelopment/maddison/data/mpd2020.xlsx"
OPENBB_BASE_URL = "http://127.0.0.1:6900"


@dataclass(frozen=True)
class BoEHeadlineField:
    col_name: str
    match: str  # exact match on the A1 "Description" row


BOE_HEADLINE_FIELDS: list[BoEHeadlineField] = [
    BoEHeadlineField(
        col_name="UK_BOE_GDP_COMPOSITE_INDEX_2013_100",
        match="Composite estimate of English and (geographically-consistent) UK real GDP at factor cost",
    ),
    BoEHeadlineField(col_name="UK_BOE_CPI_INDEX_2015_100", match="Consumer price index"),
    BoEHeadlineField(col_name="UK_BOE_CPI_INFLATION_YOY_PCT", match="Consumer price inflation"),
    BoEHeadlineField(col_name="UK_BOE_UNEMPLOYMENT_RATE_PCT", match="Unemployment rate"),
    BoEHeadlineField(col_name="UK_BOE_BANK_RATE_PCT", match="Bank Rate"),
    BoEHeadlineField(col_name="UK_BOE_10Y_GOV_BOND_YIELD_PCT", match="10 year/medium-term government bond yields"),
    BoEHeadlineField(col_name="UK_BOE_CONSOLS_YIELD_PCT", match="Consols / long-term government bond yields"),
    BoEHeadlineField(col_name="UK_BOE_SHARE_PRICES_INDEX_1962_04_100", match="Share prices"),
    BoEHeadlineField(col_name="UK_BOE_HOUSE_PRICE_INDEX_2015_01_100", match="House price index"),
    BoEHeadlineField(col_name="UK_BOE_USD_GBP_EXCHANGE_RATE", match="$/£ exchange rate"),
    BoEHeadlineField(col_name="UK_BOE_CREDIT_GBP_MN", match="Credit"),
    BoEHeadlineField(col_name="UK_BOE_BROAD_MONEY_GBP_MN", match="Broad Money"),
]


# Keep OECD calls small to avoid provider rate limits.
OECD_CPI_ONLY_COUNTRIES: list[str] = [
    "united_states",
    "japan",
    "germany",
]

# Keep MPD country scope explicit (avoid exploding to 1000s of columns).
MPD_COUNTRY_CODES: list[str] = [
    # G7
    "USA",
    "GBR",
    "DEU",
    "FRA",
    "JPN",
    "ITA",
    "CAN",
    # Major EM / large economies
    "CHN",
    "IND",
    "BRA",
    # Developed/DM add-ons
    "AUS",
    "KOR",
    "ESP",
    "NLD",
    "SWE",
]

# World Bank country scope for broad macro/fiscal/demographic/resource indicators.
WB_COUNTRY_CODES: list[str] = sorted(
    set(
        MPD_COUNTRY_CODES
        + [
            # Aggregates / regions / income groups
            "WLD",
            "EUU",
            "EMU",
            "HIC",
            "UMC",
            "LMC",
            "LIC",
            "OED",
            # Additional major economies / regions
            "MEX",
            "RUS",
            "TUR",
            "SAU",
            "IDN",
            "ZAF",
            "ARG",
            "CHE",
            "NOR",
            "SGP",
            "NZL",
            "IRL",
            "ISR",
            "POL",
            "ARE",
            "THA",
            "VNM",
            "MYS",
            "PHL",
            "CHL",
            "COL",
            "PER",
            "EGY",
            "NGA",
        ]
    )
)

# Broad World Bank indicator set to widen category coverage (post-1960 for most series).
WB_CORE_INDICATORS: list[tuple[str, str]] = [
    ("NY.GDP.MKTP.KD", "GDP_REAL_KD"),
    ("NY.GDP.MKTP.CD", "GDP_CURRENT_USD"),
    ("NY.GDP.MKTP.KD.ZG", "GDP_REAL_GROWTH_PCT"),
    ("NY.GDP.PCAP.KD", "GDP_PC_REAL_KD"),
    ("NY.GDP.PCAP.CD", "GDP_PC_CURRENT_USD"),
    ("NY.GDP.PCAP.KD.ZG", "GDP_PC_REAL_GROWTH_PCT"),
    ("NY.GNP.PCAP.KD", "GNI_PC_REAL_KD"),
    ("NY.GNP.PCAP.CD", "GNI_PC_CURRENT_USD"),
    ("NY.GDP.DEFL.KD.ZG", "GDP_DEFLATOR_YOY_PCT"),
    ("FP.CPI.TOTL.ZG", "CPI_YOY_PCT"),
    ("SL.UEM.TOTL.ZS", "UNEMPLOYMENT_PCT"),
    ("SL.TLF.CACT.ZS", "LABOR_FORCE_PARTICIPATION_PCT"),
    ("SL.EMP.TOTL.SP.ZS", "EMPLOYMENT_TO_POP_PCT"),
    ("NE.GDI.FTOT.ZS", "GROSS_CAPITAL_FORMATION_PCT_GDP"),
    ("NY.GNS.ICTR.ZS", "GROSS_SAVINGS_PCT_GDP"),
    ("NE.TRD.GNFS.ZS", "TRADE_PCT_GDP"),
    ("NE.EXP.GNFS.ZS", "EXPORTS_PCT_GDP"),
    ("NE.IMP.GNFS.ZS", "IMPORTS_PCT_GDP"),
    ("NE.CON.PRVT.ZS", "PRIVATE_CONSUMPTION_PCT_GDP"),
    ("NE.CON.GOVT.ZS", "GOVERNMENT_CONSUMPTION_PCT_GDP"),
    ("BN.CAB.XOKA.GD.ZS", "CURRENT_ACCOUNT_PCT_GDP"),
    ("BX.KLT.DINV.WD.GD.ZS", "FDI_NET_INFLOW_PCT_GDP"),
    ("GC.DOD.TOTL.GD.ZS", "GOV_DEBT_PCT_GDP"),
    ("GC.XPN.TOTL.GD.ZS", "GOV_EXP_PCT_GDP"),
    ("GC.REV.XGRT.GD.ZS", "GOV_REVENUE_PCT_GDP"),
    ("GC.TAX.TOTL.GD.ZS", "TAX_REVENUE_PCT_GDP"),
    ("GC.BAL.CASH.GD.ZS", "FISCAL_BALANCE_PCT_GDP"),
    ("FM.LBL.BMNY.GD.ZS", "BROAD_MONEY_PCT_GDP"),
    ("FS.AST.PRVT.GD.ZS", "CREDIT_PRIVATE_PCT_GDP"),
    ("FI.RES.TOTL.CD", "TOTAL_RESERVES_USD"),
    ("FI.RES.TOTL.MO", "RESERVES_MONTHS_IMPORTS"),
    ("SP.POP.TOTL", "POPULATION"),
    ("SP.URB.TOTL.IN.ZS", "URBAN_POP_PCT"),
    ("SP.DYN.LE00.IN", "LIFE_EXPECTANCY_YEARS"),
    ("SE.ADT.LITR.ZS", "ADULT_LITERACY_PCT"),
    ("SI.POV.GINI", "GINI"),
    ("NV.AGR.TOTL.ZS", "AGRI_VALUE_ADDED_PCT_GDP"),
    ("NV.IND.TOTL.ZS", "INDUSTRY_VALUE_ADDED_PCT_GDP"),
    ("NV.IND.MANF.ZS", "MANUFACTURING_VALUE_ADDED_PCT_GDP"),
    ("NV.SRV.TOTL.ZS", "SERVICES_VALUE_ADDED_PCT_GDP"),
    ("EG.USE.PCAP.KG.OE", "ENERGY_USE_PER_CAPITA"),
    ("EG.USE.ELEC.KH.PC", "ELECTRIC_POWER_CONS_PER_CAPITA"),
    ("EG.FEC.RNEW.ZS", "RENEWABLE_ENERGY_CONS_PCT"),
    ("EN.ATM.CO2E.PC", "CO2_PER_CAPITA"),
    ("NY.GDP.PETR.RT.ZS", "OIL_RENTS_PCT_GDP"),
    ("NY.GDP.NGAS.RT.ZS", "NATURAL_GAS_RENTS_PCT_GDP"),
    ("NY.GDP.COAL.RT.ZS", "COAL_RENTS_PCT_GDP"),
    ("NY.GDP.MINR.RT.ZS", "ORES_RENTS_PCT_GDP"),
]

WB_GOVERNANCE_INDICATORS: list[tuple[str, str]] = [
    ("CC.EST", "GOV_CONTROL_OF_CORRUPTION"),
    ("GE.EST", "GOV_GOVERNMENT_EFFECTIVENESS"),
    ("PV.EST", "GOV_POLITICAL_STABILITY"),
    ("RQ.EST", "GOV_REGULATORY_QUALITY"),
    ("RL.EST", "GOV_RULE_OF_LAW"),
    ("VA.EST", "GOV_VOICE_ACCOUNTABILITY"),
]


def _slug(s: str, max_len: int = 60) -> str:
    s = str(s).strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    s = s.strip("_") or "NA"
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


def _download(url: str, dest: Path, *, timeout: int = 120) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return dest
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _load_boe_a1(path: Path) -> tuple[pd.Index, pd.Series, pd.DataFrame]:
    """
    Returns:
    - year_index: Index[int] of years (out-of-bounds for Timestamp is OK here)
    - desc_row: Series of column descriptions (row 3)
    - data_rows: DataFrame indexed by year (int)
    """
    df = pd.read_excel(path, sheet_name="A1. Headline series", header=None)
    desc_row = df.iloc[3]
    years = pd.to_numeric(df.iloc[:, 0], errors="coerce")
    mask = years.notna()
    years_int = years[mask].astype(int)
    data_rows = df.loc[mask].copy()
    data_rows.index = pd.Index(years_int.values, name="year")
    return data_rows.index, desc_row, data_rows


def _find_col(desc_row: pd.Series, exact_match: str) -> int:
    for i, v in enumerate(desc_row.tolist()):
        if isinstance(v, str) and v.strip() == exact_match:
            return i
    raise KeyError(f"Cannot find BoE A1 column with description: {exact_match!r}")


def _wb_cache_path(indicator: str, country: str) -> Path:
    return Path("data/raw/worldbank") / f"{country}_{indicator}.json"


def _fetch_worldbank_series(indicator: str, *, country: str) -> pd.Series:
    cache = _wb_cache_path(indicator, country)
    cache.parent.mkdir(parents=True, exist_ok=True)

    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
    else:
        url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
        payload = None
        for attempt in range(3):
            try:
                r = requests.get(url, params={"format": "json", "per_page": 20000}, timeout=30)
                if r.status_code >= 400:
                    return pd.Series(dtype="float64")
                payload = r.json()
                cache.write_text(json.dumps(payload), encoding="utf-8")
                break
            except requests.RequestException:
                if attempt == 2:
                    return pd.Series(dtype="float64")
                time.sleep(1.5 * (attempt + 1))
        if payload is None:
            return pd.Series(dtype="float64")

    if not isinstance(payload, list) or len(payload) < 2:
        return pd.Series(dtype="float64")
    rows = payload[1] or []
    years: list[int] = []
    values: list[float] = []
    for row in rows:
        try:
            y = int(row.get("date"))
        except Exception:
            continue
        years.append(y)
        values.append(row.get("value"))
    s = pd.Series(values, index=pd.Index(years, name="year"), dtype="float64").sort_index()
    return pd.to_numeric(s, errors="coerce")


def _load_maddison_mpd2020_long(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Full data")
    required = {"countrycode", "country", "year", "gdppc", "pop"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"MPD2020 'Full data' missing columns: {sorted(missing)}")
    df = df.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["year"])
    df["year"] = df["year"].astype(int)
    df["gdppc"] = pd.to_numeric(df["gdppc"], errors="coerce")
    df["pop"] = pd.to_numeric(df["pop"], errors="coerce")
    return df


def _mpd_country_series(mpd_long: pd.DataFrame, *, countrycode: str, value_col: str) -> pd.Series:
    sub = mpd_long.loc[mpd_long["countrycode"] == countrycode, ["year", value_col]].dropna()
    if sub.empty:
        return pd.Series(dtype="float64")
    s = pd.Series(sub[value_col].values, index=pd.Index(sub["year"].values, name="year"), dtype="float64").sort_index()
    return s.groupby(level=0).last().sort_index()


def _mpd_derive_gdp_mn(gdppc_2011_intl: pd.Series, pop_thousands: pd.Series) -> pd.Series:
    """
    MPD2020 convention:
    - gdppc: 2011 international-$ per capita
    - pop:   thousands of people
    Derived GDP unit:
    - (international-$ per capita) * (thousand people) = million international-$
    """
    df = pd.concat({"gdppc": gdppc_2011_intl, "popk": pop_thousands}, axis=1)
    out = df["gdppc"] * df["popk"]
    return out.dropna().sort_index()


def _extend_by_growth(base: pd.Series, ext: pd.Series) -> pd.Series:
    """
    Extend base series to ext tail using growth ratios (unitless, avoids rebasing).
    """
    base = base.copy().sort_index()
    ext = ext.copy().sort_index()
    last_year = base.dropna().index.max() if not base.dropna().empty else None
    if last_year is None:
        return base
    tail_years = ext.index[ext.index > last_year]
    if len(tail_years) == 0:
        return base
    out = base.copy()
    for y in tail_years:
        prev = y - 1
        if prev not in out.index or prev not in ext.index:
            continue
        prev_base = out.get(prev)
        if pd.isna(prev_base):
            continue
        ratio = ext.get(y) / ext.get(prev)
        if pd.isna(ratio) or ratio <= 0:
            continue
        out.loc[y] = float(prev_base) * float(ratio)
    return out.sort_index()


def _pct_change_annual(level: pd.Series) -> pd.Series:
    return level.pct_change() * 100.0


def _openbb_cache_path(endpoint: str, params: dict[str, object]) -> Path:
    parts = [_slug(endpoint, 80)]
    for k in sorted(params.keys()):
        v = params[k]
        if v is None:
            continue
        parts.append(_slug(f"{k}={v}", 80))
    return Path("data/raw/openbb_cache") / ("__".join(parts)[:200] + ".json")


def _openbb_get(path: str, params: dict[str, object], *, timeout: int = 120) -> list[dict]:
    cache = _openbb_cache_path(path.strip("/").replace("/", "_"), params)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 10:
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return list(payload.get("results", []) or [])

    url = f"{OPENBB_BASE_URL}{path}"
    r = requests.get(url, params=params, timeout=timeout)
    if r.status_code == 204:
        return []
    if r.status_code >= 400:
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


def _monthly_to_annual_mean(m: pd.Series) -> pd.Series:
    return m.resample("YE-DEC").mean() if not m.empty else m


def _monthly_to_annual_year_end(m: pd.Series) -> pd.Series:
    return m.resample("YE-DEC").last() if not m.empty else m


def _to_year_index(a: pd.Series) -> pd.Series:
    if a.empty:
        return a
    if isinstance(a.index, pd.DatetimeIndex):
        y = pd.Index(a.index.year.astype(int), name="year")
        out = pd.Series(a.values, index=y).sort_index()
        return out.groupby(level=0).last().sort_index()
    a.index = pd.Index(pd.to_numeric(a.index, errors="coerce").astype("Int64"), name="year")
    return a.sort_index()


def _splice_additive_percent(base_pct: pd.Series, ext_pct: pd.Series) -> pd.Series:
    """
    Splice two percent series using a constant additive offset on overlap.
    ext_pct is assumed already in *percent* units (0-100).
    """
    base_pct = base_pct.copy().sort_index()
    ext_pct = ext_pct.copy().sort_index()
    overlap = pd.concat([base_pct, ext_pct], axis=1).dropna()
    offset = float(overlap.iloc[:, 0].sub(overlap.iloc[:, 1]).median()) if not overlap.empty else 0.0

    out = base_pct.copy()
    last_year = base_pct.dropna().index.max() if not base_pct.dropna().empty else None
    if last_year is None:
        return out
    tail = ext_pct[ext_pct.index > last_year]
    if not tail.empty:
        out = out.reindex(out.index.union(tail.index))
        out.loc[tail.index] = (tail + offset).values
    return out.sort_index()


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
    return df


def _summary_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        s = df[c]
        non_null = int(s.notna().sum())
        total = int(len(s))
        start = int(s.dropna().index.min()) if non_null else None
        end = int(s.dropna().index.max()) if non_null else None
        rows.append(
            {
                "column": c,
                "non_null": non_null,
                "total_years": total,
                "start_year": start,
                "end_year": end,
                "missing_pct": float((1 - non_null / total) * 100) if total else 100.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["missing_pct", "column"]).reset_index(drop=True)


def main(
    *,
    min_year: int = 1800,
    max_year: int = 2024,
    out_path: Path = Path("data/indicator_panel_annual_long_history_year.parquet"),
    summary_path: Path = Path("output/annual_long_history_summary.md"),
) -> None:
    series: dict[str, pd.Series] = {}

    # ---- BoE A1 headline (UK) ----
    boe_path = _download(BOE_XLSX_URL, Path("data/raw/boe_millennium.xlsx"))
    year_idx, desc_row, boe_rows = _load_boe_a1(boe_path)

    # Canonical BoE series
    canonical_cols: set[int] = set()
    for field in BOE_HEADLINE_FIELDS:
        col = _find_col(desc_row, field.match)
        canonical_cols.add(col)
        s = pd.to_numeric(boe_rows.iloc[:, col], errors="coerce")
        s.index = year_idx
        series[field.col_name] = s

    # Auto-add most other numeric BoE headline series (stable name = col_idx + slug(desc))
    for col_idx, desc in enumerate(desc_row.tolist()):
        if col_idx == 0 or col_idx in canonical_cols:
            continue
        if not isinstance(desc, str) or not desc.strip() or desc.strip().lower() == "description":
            continue
        s = pd.to_numeric(boe_rows.iloc[:, col_idx], errors="coerce")
        if int(s.notna().sum()) == 0:
            continue
        s.index = year_idx
        series[f"UK_BOE_A1_{col_idx:02d}_{_slug(desc)}"] = s

    # ---- WorldBank extension (UK) ----
    # GDP proxy: constant LCU; CPI proxy: CPI index (2010=100)
    wb_gdp = _fetch_worldbank_series("NY.GDP.MKTP.KN", country="GBR")
    wb_cpi = _fetch_worldbank_series("FP.CPI.TOTL", country="GBR")
    if "UK_BOE_GDP_COMPOSITE_INDEX_2013_100" in series:
        series["UK_GDP_COMPOSITE_INDEX_2013_100_EXT_WB"] = _extend_by_growth(series["UK_BOE_GDP_COMPOSITE_INDEX_2013_100"], wb_gdp)
    if "UK_BOE_CPI_INDEX_2015_100" in series:
        series["UK_CPI_INDEX_2015_100_EXT_WB"] = _extend_by_growth(series["UK_BOE_CPI_INDEX_2015_100"], wb_cpi)
        series["UK_CPI_INFLATION_YOY_PCT_EXT_WB"] = _pct_change_annual(series["UK_CPI_INDEX_2015_100_EXT_WB"])

    # ---- OECD via OpenBB: UK extensions + cross-country indicators ----
    # For rates/unemployment/cpi_yoy: OpenBB returns fractions (0.05 => 5%), convert to %.
    uk_ir_long = _to_year_index(
        _monthly_to_annual_mean(_fetch_oecd_monthly("interest_rates", country="united_kingdom", extra={"duration": "long"})) * 100.0
    )
    uk_ir_short = _to_year_index(
        _monthly_to_annual_mean(_fetch_oecd_monthly("interest_rates", country="united_kingdom", extra={"duration": "short"})) * 100.0
    )
    uk_unrate = _to_year_index(_monthly_to_annual_mean(_fetch_oecd_monthly("unemployment", country="united_kingdom")) * 100.0)
    uk_share = _to_year_index(_monthly_to_annual_year_end(_fetch_oecd_monthly("share_price_index", country="united_kingdom")))
    uk_house = _to_year_index(_monthly_to_annual_year_end(_fetch_oecd_monthly("house_price_index", country="united_kingdom")))
    uk_cli = _to_year_index(_monthly_to_annual_year_end(_fetch_oecd_monthly("composite_leading_indicator", country="united_kingdom")))

    if not uk_ir_long.empty:
        series["UK_OECD_IR_LONG_PCT"] = uk_ir_long
    if not uk_ir_short.empty:
        series["UK_OECD_IR_SHORT_PCT"] = uk_ir_short
    if not uk_unrate.empty:
        series["UK_OECD_UNEMPLOYMENT_PCT"] = uk_unrate
    if not uk_share.empty:
        series["UK_OECD_SHARE_PRICE_INDEX"] = uk_share
    if not uk_house.empty:
        series["UK_OECD_HOUSE_PRICE_INDEX"] = uk_house
    if not uk_cli.empty:
        series["UK_OECD_CLI_INDEX"] = uk_cli

    if "UK_BOE_CONSOLS_YIELD_PCT" in series and not uk_ir_long.empty:
        series["UK_BOE_CONSOLS_YIELD_PCT_EXT_OECD"] = _splice_additive_percent(series["UK_BOE_CONSOLS_YIELD_PCT"], uk_ir_long)
    if "UK_BOE_BANK_RATE_PCT" in series and not uk_ir_short.empty:
        series["UK_BOE_BANK_RATE_PCT_EXT_OECD"] = _splice_additive_percent(series["UK_BOE_BANK_RATE_PCT"], uk_ir_short)
    if "UK_BOE_UNEMPLOYMENT_RATE_PCT" in series and not uk_unrate.empty:
        series["UK_BOE_UNEMPLOYMENT_RATE_PCT_EXT_OECD"] = _splice_additive_percent(series["UK_BOE_UNEMPLOYMENT_RATE_PCT"], uk_unrate)
    if "UK_BOE_SHARE_PRICES_INDEX_1962_04_100" in series and not uk_share.empty:
        series["UK_BOE_SHARE_PRICES_INDEX_1962_04_100_EXT_OECD"] = _extend_by_growth(series["UK_BOE_SHARE_PRICES_INDEX_1962_04_100"], uk_share)
    if "UK_BOE_HOUSE_PRICE_INDEX_2015_01_100" in series and not uk_house.empty:
        series["UK_BOE_HOUSE_PRICE_INDEX_2015_01_100_EXT_OECD"] = _extend_by_growth(series["UK_BOE_HOUSE_PRICE_INDEX_2015_01_100"], uk_house)

    for c in OECD_CPI_ONLY_COUNTRIES:
        tag = c.upper()
        cpi_yoy = _fetch_oecd_monthly("cpi", country=c, extra={"transform": "yoy", "expenditure": "total"})
        if not cpi_yoy.empty:
            series[f"{tag}_OECD_CPI_YOY_PCT"] = _to_year_index(_monthly_to_annual_mean(cpi_yoy) * 100.0)

    # Euro area: OECD endpoints use inconsistent country keys across datasets.
    # - CPI / house prices: euro_area_20
    # - interest rates:     euro_area19
    # - unemployment:       euro_area20
    # - share prices:       euro_area_19
    ea_cpi = _fetch_oecd_monthly("cpi", country="euro_area_20", extra={"transform": "yoy", "expenditure": "total"})
    ea_un = _fetch_oecd_monthly("unemployment", country="euro_area20")
    ea_ir_l = _fetch_oecd_monthly("interest_rates", country="euro_area19", extra={"duration": "long"})
    ea_ir_s = _fetch_oecd_monthly("interest_rates", country="euro_area19", extra={"duration": "short"})
    ea_spx = _fetch_oecd_monthly("share_price_index", country="euro_area_19")
    ea_hpx = _fetch_oecd_monthly("house_price_index", country="euro_area_20")

    if not ea_cpi.empty:
        series["EA_OECD_CPI_YOY_PCT"] = _to_year_index(_monthly_to_annual_mean(ea_cpi) * 100.0)
    if not ea_un.empty:
        series["EA_OECD_UNEMPLOYMENT_PCT"] = _to_year_index(_monthly_to_annual_mean(ea_un) * 100.0)
    if not ea_ir_l.empty:
        series["EA_OECD_IR_LONG_PCT"] = _to_year_index(_monthly_to_annual_mean(ea_ir_l) * 100.0)
    if not ea_ir_s.empty:
        series["EA_OECD_IR_SHORT_PCT"] = _to_year_index(_monthly_to_annual_mean(ea_ir_s) * 100.0)
    if not ea_spx.empty:
        series["EA_OECD_SHARE_PRICE_INDEX"] = _to_year_index(_monthly_to_annual_year_end(ea_spx))
    if not ea_hpx.empty:
        series["EA_OECD_HOUSE_PRICE_INDEX"] = _to_year_index(_monthly_to_annual_year_end(ea_hpx))

    # ---- Shiller (US) monthly -> annual ----
    shiller_path = _download(SHILLER_XLS_URL, Path("data/raw/shiller_ie_data.xls"))
    try:
        sh = _load_shiller_monthly(shiller_path)
    except Exception:
        sh = pd.DataFrame()

    if not sh.empty:
        def s_col(name: str) -> pd.Series:
            return pd.to_numeric(sh.get(name), errors="coerce")

        # Level-like => year-end; yields => annual mean.
        spec = [
            ("US_SHILLER_SP_PRICE", "P", "year_end"),
            ("US_SHILLER_SP_DIVIDEND", "D", "year_end"),
            ("US_SHILLER_SP_EARNINGS", "E", "year_end"),
            ("US_SHILLER_CPI", "CPI", "year_end"),
            ("US_SHILLER_CAPE", "CAPE", "year_end"),
            ("US_SHILLER_GS10_YIELD_PCT", "Rate GS10", "mean"),  # already in percent
        ]
        for out_name, src_name, how in spec:
            s = s_col(src_name)
            if s.dropna().empty:
                continue
            a = _monthly_to_annual_mean(s) if how == "mean" else _monthly_to_annual_year_end(s)
            series[out_name] = _to_year_index(a)

    # ---- Maddison Project Database (MPD 2020) ----
    # Multi-country real-economy anchors (GDPpc/pop) + derived GDP.
    mpd_path = _download(MADDISON_MPD2020_XLSX_URL, Path("data/raw/maddison/mpd2020.xlsx"))
    try:
        mpd_long = _load_maddison_mpd2020_long(mpd_path)
    except Exception:
        mpd_long = pd.DataFrame()

    if not mpd_long.empty:
        for cc in MPD_COUNTRY_CODES:
            gdppc = _mpd_country_series(mpd_long, countrycode=cc, value_col="gdppc")
            popk = _mpd_country_series(mpd_long, countrycode=cc, value_col="pop")

            if not gdppc.empty:
                series[f"MPD_{cc}_GDPPC_2011_INTL"] = gdppc
            if not popk.empty:
                series[f"MPD_{cc}_POP_THOUSANDS"] = popk
            if (not gdppc.empty) and (not popk.empty):
                series[f"MPD_{cc}_GDP_MN_2011_INTL"] = _mpd_derive_gdp_mn(gdppc, popk)

            # Extend MPD tail (2019–2024) using World Bank growth splicing (unitless splice).
            # This does *not* convert levels across different unit conventions; it borrows growth rates only.
            if not gdppc.empty:
                wb_gdppc = _fetch_worldbank_series("NY.GDP.PCAP.KD", country=cc.lower())
                if not wb_gdppc.dropna().empty:
                    series[f"MPD_{cc}_GDPPC_2011_INTL_EXT_WB_GROWTH"] = _extend_by_growth(gdppc, wb_gdppc)

            if not popk.empty:
                wb_pop = _fetch_worldbank_series("SP.POP.TOTL", country=cc.lower())
                if not wb_pop.dropna().empty:
                    wb_popk = wb_pop / 1000.0
                    series[f"MPD_{cc}_POP_THOUSANDS_EXT_WB_GROWTH"] = _extend_by_growth(popk, wb_popk)

            gdppc_ext = series.get(f"MPD_{cc}_GDPPC_2011_INTL_EXT_WB_GROWTH")
            popk_ext = series.get(f"MPD_{cc}_POP_THOUSANDS_EXT_WB_GROWTH")
            if isinstance(gdppc_ext, pd.Series) and isinstance(popk_ext, pd.Series):
                gdp_ext = _mpd_derive_gdp_mn(gdppc_ext, popk_ext)
                if not gdp_ext.empty:
                    series[f"MPD_{cc}_GDP_MN_2011_INTL_EXT_WB_GROWTH"] = gdp_ext

    # ---- World Bank broad macro/fiscal/demographic/resource indicators ----
    for cc in WB_COUNTRY_CODES:
        for indicator, suffix in WB_CORE_INDICATORS:
            wb = _fetch_worldbank_series(indicator, country=cc.lower())
            if not wb.dropna().empty:
                series[f"WB_{cc}_{suffix}"] = _to_year_index(wb)
        for indicator, suffix in WB_GOVERNANCE_INDICATORS:
            wb = _fetch_worldbank_series(indicator, country=cc.lower())
            if not wb.dropna().empty:
                series[f"WB_{cc}_{suffix}"] = _to_year_index(wb)

    # ---- Final frame ----
    df = pd.DataFrame(series).sort_index()
    df = df[(df.index >= min_year) & (df.index <= max_year)]
    df = df.reindex(pd.Index(range(min_year, max_year + 1), name="year"))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)

    summ = _summary_table(df)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Annual long-history panel (year index)",
        "",
        f"- Output: `{out_path}`",
        f"- Year range requested: {min_year}–{max_year}",
        f"- Panel shape: {df.shape[0]} years × {df.shape[1]} columns",
        "- Note: year index is integer (pre-1677 timestamps are out-of-bounds for pandas)",
        "- Notes on extensions:",
        "  - `*_EXT_WB`: extended by WorldBank growth ratios (unitless splice).",
        "  - `*_EXT_WB_GROWTH`: extended by WorldBank growth ratios (unitless splice; used for MPD tail extension).",
        "  - `*_EXT_OECD`: extended by OECD via OpenBB (rates: additive-offset splice; indices: growth-ratio splice).",
        "",
        "## Coverage summary",
        "",
        summ.to_markdown(index=False),
        "",
    ]
    summary_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
