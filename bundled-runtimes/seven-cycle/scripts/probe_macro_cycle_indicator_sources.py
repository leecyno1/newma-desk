""" 
Probe indicator availability for macro/cycle research across:
- Tushare Pro (China macro + money + PMI + rates)
- AkShare (China macro enrichment)
- OpenBB (global macro + indices + Fama-French)

Outputs:
- output/macro_cycle_indicator_availability.csv  (full results)
- output/macro_cycle_indicator_availability.md   (summary + top tables)

The goal is to answer: for a broad set of macro/cycle indicators, can we fetch data,
and how complete is it on:
- Monthly window: 2000-01 to 2024-12 (month-end)
- Annual window:  1960 to 2024 (year-end)

Run:
  export TUSHARE_TOKEN=...  # your token
  source .venv2/bin/activate
  python scripts/probe_macro_cycle_indicator_sources.py --sources tushare,akshare,openbb
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import os
import pandas as pd

DEFAULT_OPENBB_BASE_URL = "http://127.0.0.1:6900"

MONTHLY_START = pd.Timestamp("2000-01-31")
MONTHLY_END = pd.Timestamp("2024-12-31")
ANNUAL_START = pd.Timestamp("1960-12-31")
ANNUAL_END = pd.Timestamp("2024-12-31")

MONTHLY_INDEX = pd.date_range(MONTHLY_START, MONTHLY_END, freq="ME")
ANNUAL_INDEX = pd.date_range(ANNUAL_START, ANNUAL_END, freq="YE-DEC")


@dataclass
class SeriesResult:
    indicator_id: str
    name: str
    category: str
    source: str
    base_freq: str
    status: str
    message: str
    first_date: Optional[pd.Timestamp]
    last_date: Optional[pd.Timestamp]
    monthly_coverage: float
    monthly_missing: int
    monthly_complete: bool
    annual_coverage: float
    annual_missing: int
    annual_complete: bool


def _coverage_on_index(s: pd.Series, idx: pd.DatetimeIndex) -> Tuple[float, int, bool]:
    s2 = s.reindex(idx)
    missing = int(s2.isna().sum())
    cov = float(1.0 - missing / len(idx)) if len(idx) else 0.0
    return cov, missing, missing == 0


def _infer_base_freq(idx: pd.DatetimeIndex) -> str:
    if len(idx) < 4:
        return "?"
    diffs = idx.to_series().diff().dropna().dt.days
    if diffs.empty:
        return "?"
    med = float(diffs.median())
    if med <= 7:
        return "D"
    if med <= 40:
        return "M"
    if med <= 120:
        return "Q"
    return "A"


def _to_month_end(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.to_period("M").to_timestamp("M")


def _parse_chinese_yyyymm(values: pd.Series) -> pd.DatetimeIndex:
    s = values.astype(str)
    year = pd.to_numeric(s.str.extract(r"(\d{4})")[0], errors="coerce")
    month = pd.to_numeric(s.str.extract(r"年(\d{1,2})")[0], errors="coerce")
    dt = pd.to_datetime(pd.DataFrame({"year": year, "month": month, "day": 1}), errors="coerce")
    dt = dt.dt.to_period("M").dt.to_timestamp("M")
    return pd.DatetimeIndex(dt)


def _detect_date_column(df: pd.DataFrame) -> Optional[str]:
    for col in df.columns:
        c = str(col)
        if c in {"date", "DATE", "month", "MONTH", "quarter", "QUARTER", "月份", "日期"}:
            return str(col)
    for col in df.columns:
        c = str(col)
        if any(k in c for k in ["日期", "时间", "月份", "month", "MONTH", "date", "DATE", "quarter", "QUARTER"]):
            return str(col)
    if len(df.columns) > 0:
        return str(df.columns[0])
    return None


def _parse_time_index(df: pd.DataFrame, date_col: str) -> pd.DatetimeIndex:
    col = df[date_col]

    if pd.api.types.is_datetime64_any_dtype(col):
        return pd.DatetimeIndex(col)

    if pd.api.types.is_numeric_dtype(col):
        s = pd.to_numeric(col, errors="coerce").astype("Int64").astype(str)
        mode_len = int(s.str.len().mode().iloc[0]) if not s.empty else 0
        if mode_len == 8:
            return pd.DatetimeIndex(pd.to_datetime(s, format="%Y%m%d", errors="coerce"))
        if mode_len == 6:
            dt = pd.to_datetime(s, format="%Y%m", errors="coerce").dt.to_period("M").dt.to_timestamp("M")
            return pd.DatetimeIndex(dt)

    s = col.astype(str).str.strip()

    # Common YYYYMM / YYYYMMDD encodings stored as strings.
    non_empty = s.replace({"": pd.NA}).dropna()
    if not non_empty.empty:
        sample = non_empty.head(50)
        if sample.str.fullmatch(r"\d{6}", na=False).mean() >= 0.8:
            dt = pd.to_datetime(s, format="%Y%m", errors="coerce").dt.to_period("M").dt.to_timestamp("M")
            return pd.DatetimeIndex(dt)
        if sample.str.fullmatch(r"\d{8}", na=False).mean() >= 0.8:
            return pd.DatetimeIndex(pd.to_datetime(s, format="%Y%m%d", errors="coerce"))

    if s.str.contains(r"Q\d", regex=True, na=False).any() or date_col.lower() in {"quarter", "quar"}:
        dt = pd.PeriodIndex(s, freq="Q").to_timestamp("Q")
        return pd.DatetimeIndex(dt)

    if s.str.contains("年", na=False).any() and s.str.contains("月", na=False).any():
        return _parse_chinese_yyyymm(s)

    return pd.DatetimeIndex(pd.to_datetime(col, errors="coerce"))


def _df_numeric_series(df: pd.DataFrame, date_col: str) -> Tuple[pd.DataFrame, str]:
    tmp = df.copy()
    idx = _parse_time_index(tmp, date_col)
    tmp = tmp.drop(columns=[date_col], errors="ignore")
    tmp.index = idx
    tmp = tmp.sort_index()

    for c in tmp.columns:
        tmp[c] = pd.to_numeric(tmp[c], errors="coerce")

    base_freq = _infer_base_freq(tmp.index)
    return tmp, base_freq


@dataclass(frozen=True)
class TushareEndpointSpec:
    api_name: str
    base_name: str
    date_col_hint: str
    category: str
    params: dict[str, object]


def probe_tushare(endpoints: Optional[list[TushareEndpointSpec]] = None) -> List[SeriesResult]:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing TUSHARE_TOKEN for Tushare Pro probe.")

    import tushare as ts  # type: ignore

    ts.set_token(token)
    pro = ts.pro_api()

    if endpoints is None:
        endpoints = [
            TushareEndpointSpec("cn_cpi", "CN_CPI", "month", "China/Inflation", {}),
            TushareEndpointSpec("cn_ppi", "CN_PPI", "month", "China/Inflation", {}),
            TushareEndpointSpec("cn_m", "CN_MONEY", "month", "China/MoneyCredit", {}),
            TushareEndpointSpec("cn_gdp", "CN_GDP", "quarter", "China/Growth", {}),
            TushareEndpointSpec("cn_pmi", "CN_PMI", "MONTH", "China/Growth", {}),
            TushareEndpointSpec("shibor", "SHIBOR", "date", "China/Rates", {}),
            TushareEndpointSpec("hibor", "HIBOR", "date", "HK/Rates", {}),
            TushareEndpointSpec("shibor_quote", "SHIBOR_QUOTE", "date", "China/Rates", {}),
            # Representative China equity indices (daily)
            TushareEndpointSpec(
                "index_daily",
                "IDX_SH_COMP",
                "trade_date",
                "China/Equity",
                {"ts_code": "000001.SH", "start_date": "19900101"},
            ),
            TushareEndpointSpec(
                "index_daily",
                "IDX_HS300",
                "trade_date",
                "China/Equity",
                {"ts_code": "000300.SH", "start_date": "19900101"},
            ),
            TushareEndpointSpec(
                "index_daily",
                "IDX_CSI500",
                "trade_date",
                "China/Equity",
                {"ts_code": "000905.SH", "start_date": "19900101"},
            ),
            TushareEndpointSpec(
                "index_daily",
                "IDX_CSI1000",
                "trade_date",
                "China/Equity",
                {"ts_code": "000852.SH", "start_date": "20050101"},
            ),
            # Index daily basic (valuation + turnover) if available on your subscription
            TushareEndpointSpec(
                "index_dailybasic",
                "IDX_DAILYBASIC_HS300",
                "trade_date",
                "China/EquityValuation",
                {"ts_code": "000300.SH", "start_date": "20040101"},
            ),
        ]

    results: List[SeriesResult] = []

    for ep in endpoints:
        api_name = ep.api_name
        base_name = ep.base_name
        date_col_hint = ep.date_col_hint
        category = ep.category
        try:
            df = getattr(pro, api_name)(**ep.params)
            if df is None or df.empty:
                continue

            date_col = date_col_hint if date_col_hint in df.columns else _detect_date_column(df) or date_col_hint
            if date_col not in df.columns:
                continue

            tmp, base_freq = _df_numeric_series(df, date_col)
            numeric_cols = [c for c in tmp.columns if pd.api.types.is_numeric_dtype(tmp[c])]
            if not numeric_cols:
                continue

            for c in numeric_cols:
                s = tmp[c]
                if s.dropna().shape[0] < 24:
                    continue

                if base_freq == "D":
                    s_m = s.resample("ME").last()
                else:
                    s_m = s.copy()
                    s_m.index = _to_month_end(s_m.index)
                    s_m = s_m.groupby(s_m.index).last().sort_index()

                s_a = s_m.resample("YE-DEC").last()

                m_cov, m_missing, m_complete = _coverage_on_index(s_m, MONTHLY_INDEX)
                a_cov, a_missing, a_complete = _coverage_on_index(s_a, ANNUAL_INDEX)

                non_na = s.dropna()

                results.append(
                    SeriesResult(
                        indicator_id=f"TS:{api_name}:{base_name}:{c}",
                        name=f"{base_name}.{c}",
                        category=category,
                        source="tushare",
                        base_freq=base_freq,
                        status="ok",
                        message="",
                        first_date=non_na.index.min() if not non_na.empty else None,
                        last_date=non_na.index.max() if not non_na.empty else None,
                        monthly_coverage=m_cov,
                        monthly_missing=m_missing,
                        monthly_complete=m_complete,
                        annual_coverage=a_cov,
                        annual_missing=a_missing,
                        annual_complete=a_complete,
                    )
                )

        except Exception as e:
            results.append(
                SeriesResult(
                    indicator_id=f"TS:{api_name}:{base_name}",
                    name=base_name,
                    category=category,
                    source="tushare",
                    base_freq="?",
                    status="error",
                    message=str(e),
                    first_date=None,
                    last_date=None,
                    monthly_coverage=0.0,
                    monthly_missing=len(MONTHLY_INDEX),
                    monthly_complete=False,
                    annual_coverage=0.0,
                    annual_missing=len(ANNUAL_INDEX),
                    annual_complete=False,
                )
            )

    return results


AKSHARE_CURATED_FUNCTIONS: list[str] = [
    # Growth / activity
    "macro_china_gdp",
    "macro_china_gdzctz",
    "macro_china_industrial_production_yoy",
    "macro_china_gyzjz",
    "macro_china_consumer_goods_retail",
    "macro_china_exports_yoy",
    "macro_china_imports_yoy",
    "macro_china_trade_balance",
    "macro_china_society_electricity",
    "macro_china_society_traffic_volume",
    "macro_china_freight_index",
    "macro_china_new_house_price",
    "macro_china_real_estate",
    # Prices / inflation
    "macro_china_cpi",
    "macro_china_ppi",
    "macro_china_commodity_price_index",
    # Money / credit
    "macro_china_money_supply",
    "macro_china_shrzgm",
    "macro_china_new_financial_credit",
    "macro_china_reserve_requirement_ratio",
    # Rates
    "macro_china_lpr",
    "macro_china_shibor_all",
    "macro_china_swap_rate",
    # Equity / liquidity
    "macro_china_market_margin_sh",
    "macro_china_market_margin_sz",
    "macro_china_stock_market_cap",
]


def _call_with_timeout(fn, timeout_s: Optional[int]):
    if not timeout_s or timeout_s <= 0:
        return fn()
    try:
        import signal

        if not hasattr(signal, "SIGALRM"):
            return fn()

        class _Timeout(Exception):
            pass

        def _handler(signum, frame):  # noqa: ARG001
            raise _Timeout("timeout")

        old = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(int(timeout_s))
        try:
            return fn()
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)
    except Exception:
        # Best-effort timeout; if anything goes wrong with signal handling, fall back.
        return fn()


def probe_akshare(
    mode: str = "curated",
    max_functions: Optional[int] = None,
    timeout_s: Optional[int] = 20,
) -> List[SeriesResult]:
    import inspect
    import akshare as ak  # type: ignore

    all_fnames = sorted([n for n in dir(ak) if n.startswith("macro_china_")])

    if mode == "curated":
        fnames = [n for n in AKSHARE_CURATED_FUNCTIONS if n in all_fnames]
    elif mode == "scan":
        fnames = all_fnames
    else:
        raise ValueError(f"Unsupported akshare mode: {mode}")

    if max_functions is not None:
        fnames = fnames[:max_functions]

    results: List[SeriesResult] = []

    for fname in fnames:
        f = getattr(ak, fname, None)
        if not callable(f):
            continue

        try:
            sig = inspect.signature(f)
            required = [
                p
                for p in sig.parameters.values()
                if p.default is inspect._empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
            ]
            if required:
                continue

            df = _call_with_timeout(f, timeout_s)
            if df is None or not isinstance(df, pd.DataFrame) or df.empty:
                continue

            date_col = _detect_date_column(df)
            if not date_col or date_col not in df.columns:
                continue

            tmp, base_freq = _df_numeric_series(df, date_col)
            numeric_cols = [c for c in tmp.columns if pd.api.types.is_numeric_dtype(tmp[c])]
            if not numeric_cols:
                continue

            category = "China/Macro(AkShare)"

            for c in numeric_cols:
                s = tmp[c]
                if s.dropna().shape[0] < 24:
                    continue

                if base_freq == "D":
                    s_m = s.resample("ME").last()
                else:
                    s_m = s.copy()
                    s_m.index = _to_month_end(s_m.index)
                    s_m = s_m.groupby(s_m.index).last().sort_index()

                s_a = s_m.resample("YE-DEC").last()

                m_cov, m_missing, m_complete = _coverage_on_index(s_m, MONTHLY_INDEX)
                a_cov, a_missing, a_complete = _coverage_on_index(s_a, ANNUAL_INDEX)

                non_na = s.dropna()
                results.append(
                    SeriesResult(
                        indicator_id=f"AK:{fname}:{c}",
                        name=f"{fname}.{c}",
                        category=category,
                        source="akshare",
                        base_freq=base_freq,
                        status="ok",
                        message="",
                        first_date=non_na.index.min() if not non_na.empty else None,
                        last_date=non_na.index.max() if not non_na.empty else None,
                        monthly_coverage=m_cov,
                        monthly_missing=m_missing,
                        monthly_complete=m_complete,
                        annual_coverage=a_cov,
                        annual_missing=a_missing,
                        annual_complete=a_complete,
                    )
                )

        except Exception:
            continue

    return results


def probe_openbb(base_url: str = DEFAULT_OPENBB_BASE_URL) -> List[SeriesResult]:
    import requests

    results: List[SeriesResult] = []

    def _add_series(indicator_id: str, name: str, category: str, s: pd.Series) -> None:
        if s is None or s.empty:
            return
        s = s.sort_index()
        non_na = s.dropna()
        if non_na.shape[0] < 24:
            return

        base_freq = _infer_base_freq(pd.DatetimeIndex(s.index))

        if base_freq == "D":
            s_m = s.resample("ME").last()
        else:
            s_m = s.copy()
            s_m.index = _to_month_end(pd.DatetimeIndex(s_m.index))
            s_m = s_m.groupby(s_m.index).last().sort_index()

        s_a = s_m.resample("YE-DEC").last()

        m_cov, m_missing, m_complete = _coverage_on_index(s_m, MONTHLY_INDEX)
        a_cov, a_missing, a_complete = _coverage_on_index(s_a, ANNUAL_INDEX)

        results.append(
            SeriesResult(
                indicator_id=indicator_id,
                name=name,
                category=category,
                source="openbb",
                base_freq=base_freq,
                status="ok",
                message="",
                first_date=non_na.index.min() if not non_na.empty else None,
                last_date=non_na.index.max() if not non_na.empty else None,
                monthly_coverage=m_cov,
                monthly_missing=m_missing,
                monthly_complete=m_complete,
                annual_coverage=a_cov,
                annual_missing=a_missing,
                annual_complete=a_complete,
            )
        )

    # 1) Global indices / FX / commodities via yfinance (daily)
    yfinance_symbols = {
        "^GSPC": "US SPX (adj close)",
        "^NDX": "US NDX (adj close)",
        "^DJI": "US DJI (adj close)",
        "^N225": "JP Nikkei225 (adj close)",
        "^STOXX50E": "EU STOXX50E (adj close)",
        "GC=F": "Gold futures (adj close)",
        "SI=F": "Silver futures (adj close)",
        "CL=F": "WTI crude futures (adj close)",
        "HG=F": "Copper futures (adj close)",
        "USDCNY=X": "USD/CNY (adj close)",
        "DX-Y.NYB": "DXY (adj close)",
    }
    for symbol, label in yfinance_symbols.items():
        url = f"{base_url}/api/v1/index/price/historical"
        params = {"provider": "yfinance", "symbol": symbol, "start_date": "1960-01-01", "end_date": "2024-12-31"}
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json().get("results", [])
            if not data:
                continue
            df = pd.DataFrame(data)
            if "date" not in df.columns:
                continue
            df["date"] = pd.to_datetime(df["date"])
            price_col = "adj_close" if "adj_close" in df.columns else "close"
            s = pd.to_numeric(df[price_col], errors="coerce")
            s.index = pd.DatetimeIndex(df["date"])
            _add_series(f"OBB:index_price:{symbol}:{price_col}", label, "Global/Market", s)
        except Exception:
            continue

    # 2) OECD macro (no key required)
    oecd_series = [
        (
            "cpi",
            {"country": "united_states", "transform": "yoy", "frequency": "monthly", "expenditure": "total"},
            "OBB:oecd:cpi:united_states:yoy:total",
            "US CPI YoY (OECD)",
            "Global/Macro",
        ),
        (
            "unemployment",
            {"country": "united_states", "frequency": "monthly"},
            "OBB:oecd:unemployment:united_states",
            "US Unemployment (OECD)",
            "Global/Macro",
        ),
        (
            "interest_rates",
            {"country": "united_states", "duration": "short", "frequency": "monthly"},
            "OBB:oecd:interest_rates:united_states:short",
            "US Short Rate (OECD)",
            "Global/Rates",
        ),
        (
            "interest_rates",
            {"country": "united_states", "duration": "long", "frequency": "monthly"},
            "OBB:oecd:interest_rates:united_states:long",
            "US Long Rate (OECD)",
            "Global/Rates",
        ),
    ]
    for endpoint, extra_params, indicator_id, label, category in oecd_series:
        url = f"{base_url}/api/v1/economy/{endpoint}"
        params = {"provider": "oecd", "start_date": "1960-01-01", "end_date": "2024-12-31"} | extra_params
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            data = r.json().get("results", [])
            if not data:
                continue
            df = pd.DataFrame(data)
            if "date" not in df.columns or "value" not in df.columns:
                continue
            df["date"] = pd.to_datetime(df["date"])
            s = pd.to_numeric(df["value"], errors="coerce")
            s.index = pd.DatetimeIndex(df["date"]).to_period("M").to_timestamp("M")
            _add_series(indicator_id, label, category, s)
        except Exception:
            continue

    # 3) Fama-French industry portfolios (monthly, long history)
    ff_url = f"{base_url}/api/v1/famafrench/us_portfolio_returns"
    ff_params = {
        "portfolio": "17_industry_portfolios",
        "frequency": "monthly",
        "start_date": "1960-01-01",
        "end_date": "2024-12-31",
    }
    try:
        r = requests.get(ff_url, params=ff_params, timeout=120)
        r.raise_for_status()
        data = r.json().get("results", [])
        if data:
            df = pd.DataFrame(data)
            if {"date", "portfolio", "value"}.issubset(df.columns):
                df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp("M")
                df["value"] = pd.to_numeric(df["value"], errors="coerce")
                for portfolio_name, sub in df.groupby("portfolio"):
                    s = sub.set_index("date")["value"].sort_index()
                    _add_series(
                        f"OBB:ff:17_industry_portfolios:{portfolio_name}",
                        f"FF 17 Industry: {portfolio_name} (monthly %)",
                        "US/IndustryPortfolioReturns",
                        s,
                    )
    except Exception:
        pass

    return results


def write_reports(results: List[SeriesResult]) -> None:
    df = pd.DataFrame([r.__dict__ for r in results])
    if df.empty:
        raise RuntimeError("No results produced")

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "macro_cycle_indicator_availability.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8")

    def summary_block(title: str, sub: pd.DataFrame) -> str:
        lines: List[str] = []
        lines.append(f"## {title}")
        lines.append("")
        lines.append(f"- Indicators: {sub.shape[0]}")
        lines.append(f"- Monthly complete (2000-2024): {int(sub['monthly_complete'].sum())}")
        lines.append(f"- Annual complete (1960-2024): {int(sub['annual_complete'].sum())}")
        lines.append("")
        top = sub.sort_values(["monthly_coverage", "annual_coverage"], ascending=False).head(40)
        cols = [
            "indicator_id",
            "name",
            "base_freq",
            "first_date",
            "last_date",
            "monthly_coverage",
            "annual_coverage",
            "monthly_complete",
            "annual_complete",
        ]
        lines.append("Top 40 by coverage:")
        lines.append("")
        lines.append(top[cols].to_markdown(index=False))
        lines.append("")
        return "\n".join(lines)

    md_lines: List[str] = []
    md_lines.append("# Macro/Cycle Indicator Availability Report")
    md_lines.append("")
    md_lines.append("本报告用于回答：宏观与周期研究需要的指标，是否能在当前数据源中找到，并且是否足够完整。")
    md_lines.append("")
    md_lines.append("## Coverage windows")
    md_lines.append("")
    md_lines.append(f"- Monthly: {MONTHLY_START.date()} ~ {MONTHLY_END.date()} (month-end, {len(MONTHLY_INDEX)} points)")
    md_lines.append(f"- Annual:  {ANNUAL_START.date()} ~ {ANNUAL_END.date()} (year-end, {len(ANNUAL_INDEX)} points)")
    md_lines.append("")

    md_lines.append(summary_block("Tushare Pro", df[df["source"] == "tushare"]))
    md_lines.append(summary_block("AkShare", df[df["source"] == "akshare"]))
    md_lines.append(summary_block("Overall", df))

    md_path = out_dir / "macro_cycle_indicator_availability.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe macro/cycle indicator availability across data sources.")
    parser.add_argument(
        "--sources",
        default="tushare,akshare,openbb",
        help="Comma-separated sources to probe: tushare, akshare, openbb",
    )
    parser.add_argument(
        "--akshare-mode",
        default="curated",
        choices=["curated", "scan"],
        help="AkShare probe mode: curated allowlist (fast) or scan all macro_china_* (slower).",
    )
    parser.add_argument("--max-akshare", type=int, default=None, help="Limit number of AkShare functions to probe.")
    parser.add_argument("--akshare-timeout", type=int, default=20, help="Timeout per AkShare function (seconds).")
    parser.add_argument("--openbb-base-url", default=DEFAULT_OPENBB_BASE_URL, help="Base URL for local OpenBB API.")
    args = parser.parse_args()

    sources = {s.strip().lower() for s in str(args.sources).split(",") if s.strip()}

    results: List[SeriesResult] = []
    if "tushare" in sources:
        results.extend(probe_tushare())
    if "akshare" in sources:
        results.extend(probe_akshare(mode=args.akshare_mode, max_functions=args.max_akshare, timeout_s=args.akshare_timeout))
    if "openbb" in sources:
        results.extend(probe_openbb(base_url=args.openbb_base_url))
    write_reports(results)


if __name__ == "__main__":
    main()
