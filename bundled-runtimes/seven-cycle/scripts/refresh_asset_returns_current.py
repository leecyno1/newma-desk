"""Incrementally refresh the current monthly returns used by asset research."""

from __future__ import annotations

from pathlib import Path
import argparse
from datetime import date
import csv
import io
import json
import os
import zipfile

import pandas as pd
import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "asset_returns_current_refresh.json"
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_monthly.parquet"

CN_INDEX_SPECS = {
    ("A股宽基指数", "中证1000"): "000852.SH",
    ("A股宽基指数", "中证500"): "000905.SH",
    ("A股宽基指数", "沪深300"): "000300.SH",
    ("风格/规模指数", "上证小盘"): "000045.SH",
    ("风格/规模指数", "中小盘(深证)"): "399401.SZ",
    ("风格/规模指数", "中证A500"): "000510.SH",
    ("风格/规模指数", "全指成长"): "000057.SH",
    ("风格/规模指数", "创业板50"): "399673.SZ",
    ("风格/规模指数", "创业板指"): "399006.SZ",
    ("风格/规模指数", "创质量"): "399269.SZ",
    ("风格/规模指数", "科创50"): "000688.SH",
    ("风格/规模指数", "红利指数(上证)"): "000015.SH",
    ("风格/规模指数", "超大盘"): "000043.SH",
    ("各类债券指数", "国债指数(上证)"): "000012.SH",
    ("各类债券指数", "沪公司债"): "000022.SH",
    ("各类债券指数", "深信用债"): "399301.SZ",
    ("各类债券指数", "深公司债"): "399302.SZ",
    ("各类债券指数", "企债指数(深证)"): "399481.SZ",
    ("各类债券指数", "国证转债"): "399413.SZ",
    ("各类债券指数", "上证转债"): "000139.SH",
    ("各类债券指数", "深证转债"): "399307.SZ",
    ("各类债券指数", "深转交债"): "399290.SZ",
}

CN_ETF_SPECS = {
    ("A股宽基指数", "中证1000(ETF累计净值)"): "512100",
    ("A股宽基指数", "中证500(ETF累计净值)"): "510500",
    ("A股宽基指数", "沪深300(ETF累计净值)"): "510300",
    ("风格/规模指数", "创业板50(ETF累计净值)"): "159949",
    ("风格/规模指数", "创业板指(ETF累计净值)"): "159915",
    ("风格/规模指数", "科创50(ETF累计净值)"): "588000",
    ("风格/规模指数", "红利(ETF累计净值)"): "510880",
}

GLOBAL_YAHOO_SPECS = {
    ("海外指数/ETF", "标普500(SPY)"): "SPY",
    ("海外指数/ETF", "纳指100(QQQ)"): "QQQ",
    ("海外指数/ETF", "罗素2000(IWM)"): "IWM",
    ("海外指数/ETF", "德国ETF(EWG)"): "EWG",
    ("海外指数/ETF", "印度ETF(INDA)"): "INDA",
    ("海外指数/ETF", "英国富时100(^FTSE)"): "^FTSE",
    ("海外指数/ETF", "法国CAC40(^FCHI)"): "^FCHI",
    ("美股行业ETF", "美股可选消费(XLY)"): "XLY",
    ("美股行业ETF", "美股必选消费(XLP)"): "XLP",
    ("美股行业ETF", "美股能源(XLE)"): "XLE",
    ("美股行业ETF", "美股金融(XLF)"): "XLF",
    ("美股行业ETF", "美股工业(XLI)"): "XLI",
    ("美股行业ETF", "美股信息科技(XLK)"): "XLK",
    ("美股行业ETF", "美股公用事业(XLU)"): "XLU",
    ("美股行业ETF", "美股医疗保健(XLV)"): "XLV",
    ("美股行业ETF", "美股原材料(XLB)"): "XLB",
    ("商品", "黄金"): "GC=F",
    ("商品", "铜"): "HG=F",
    ("商品", "原油"): "CL=F",
    ("外汇", "美元指数DXY"): "DX-Y.NYB",
}

LOCAL_PANEL_SPECS = {
    ("商品", "中国大宗商品价格综合指数"): "CN_COMMODITY_PRICE_INDEX_AK_LEVEL",
}

FF17_CATEGORY = "FF 17行业组合(US)"
FF17_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "17_Industry_Portfolios_CSV.zip"
)


def _month_end(value: str | pd.Timestamp | date) -> pd.Timestamp:
    return pd.Timestamp(value).to_period("M").to_timestamp("M")


def _monthly_returns(level: pd.Series) -> pd.Series:
    level = pd.to_numeric(level, errors="coerce").dropna().sort_index()
    level.index = pd.to_datetime(level.index).to_period("M").to_timestamp("M")
    level = level.groupby(level.index).last()
    return level.pct_change(fill_method=None)


def _daily_close_returns(
    frame: pd.DataFrame,
    *,
    date_column: str,
    value_column: str,
) -> pd.Series:
    dates = pd.to_datetime(frame[date_column].astype(str), errors="coerce")
    values = pd.to_numeric(frame[value_column], errors="coerce")
    level = (
        pd.Series(values.to_numpy(), index=dates)
        .dropna()
        .sort_index()
        .resample("ME")
        .last()
    )
    return _monthly_returns(level)


def _merge_returns(
    frame: pd.DataFrame,
    key: tuple[str, str],
    series: pd.Series,
    *,
    start: pd.Timestamp,
    through: pd.Timestamp,
) -> pd.DataFrame:
    if key not in frame.columns:
        raise KeyError(f"Unknown asset column: {key}")
    update = pd.to_numeric(series, errors="coerce").loc[start:through].dropna()
    if update.empty:
        return frame
    frame = frame.reindex(frame.index.union(update.index).sort_values())
    frame.loc[update.index, key] = update.to_numpy()
    return frame


def _yahoo_monthly(
    symbol: str,
    *,
    start: pd.Timestamp,
    through: pd.Timestamp,
) -> pd.Series:
    encoded_symbol = requests.utils.quote(symbol, safe="")
    response = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}",
        params={
            "period1": int((start - pd.offsets.MonthEnd(2)).timestamp()),
            "period2": int(
                (through + pd.offsets.MonthEnd(1) + pd.Timedelta(days=1)).timestamp()
            ),
            "interval": "1d",
            "events": "div,splits",
        },
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    result = response.json().get("chart", {}).get("result") or []
    if not result:
        return pd.Series(dtype=float)
    payload = result[0]
    timestamps = pd.to_datetime(payload.get("timestamp", []), unit="s")
    indicators = payload.get("indicators", {})
    adjusted = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    values = adjusted or (indicators.get("quote") or [{}])[0].get("close") or []
    level = pd.Series(pd.to_numeric(values, errors="coerce"), index=timestamps)
    return _monthly_returns(level)


def _parse_ken_french_17_monthly(text: str) -> pd.DataFrame:
    lines = text.splitlines()
    section_index = next(
        index
        for index, line in enumerate(lines)
        if "Average Value Weighted Returns -- Monthly" in line
    )
    reader = csv.reader(lines[section_index + 1 :])
    columns = next(reader)[1:]
    rows: list[list[str]] = []
    dates: list[pd.Timestamp] = []
    for row in reader:
        if not row or not row[0].strip().isdigit() or len(row[0].strip()) != 6:
            break
        dates.append(
            pd.to_datetime(row[0].strip(), format="%Y%m").to_period("M").to_timestamp("M")
        )
        rows.append(row[1:])
    frame = pd.DataFrame(rows, index=dates, columns=columns).apply(
        pd.to_numeric,
        errors="coerce",
    )
    return frame.mask(frame <= -99.0) / 100.0


def _ken_french_17_monthly() -> pd.DataFrame:
    response = requests.get(
        FF17_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        filename = archive.namelist()[0]
        text = archive.read(filename).decode("utf-8", errors="replace")
    return _parse_ken_french_17_monthly(text)


def refresh_ff17_returns(
    frame: pd.DataFrame,
    *,
    through: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    monthly = _ken_french_17_monthly()
    refreshed: list[tuple[str, str]] = []
    for name in frame[FF17_CATEGORY].columns:
        key = (FF17_CATEGORY, name)
        frame = _merge_returns(
            frame,
            key,
            monthly[name],
            start=frame.index.min(),
            through=through,
        )
        refreshed.append(key)
    latest = max(frame[key].last_valid_index() for key in refreshed)
    return frame.sort_index(), {
        "source": "Ken French Data Library 17 Industry Portfolios, value weighted monthly returns",
        "sourceUrl": FF17_URL,
        "through": through.strftime("%Y-%m"),
        "sourceDataEnd": latest.strftime("%Y-%m"),
        "refreshedAssets": len(refreshed),
        "refreshed": ["||".join(key) for key in refreshed],
    }


def refresh_returns(
    frame: pd.DataFrame,
    pro: object,
    *,
    start: pd.Timestamp,
    through: pd.Timestamp,
) -> tuple[pd.DataFrame, dict[str, object]]:
    fetch_start = (start - pd.offsets.MonthEnd(2)).strftime("%Y%m%d")
    fetch_end = through.strftime("%Y%m%d")
    refreshed: list[tuple[str, str]] = []

    missing_columns = [
        key
        for key in (*GLOBAL_YAHOO_SPECS, *LOCAL_PANEL_SPECS)
        if key not in frame.columns
    ]
    for key in missing_columns:
        frame[key] = float("nan")
    frame = frame.sort_index(axis=1)

    for key, ts_code in CN_INDEX_SPECS.items():
        data = pro.index_daily(
            ts_code=ts_code,
            start_date=fetch_start,
            end_date=fetch_end,
        )
        series = _daily_close_returns(
            data,
            date_column="trade_date",
            value_column="close",
        )
        frame = _merge_returns(frame, key, series, start=start, through=through)
        refreshed.append(key)

    import akshare as ak

    for key, code in CN_ETF_SPECS.items():
        data = ak.fund_open_fund_info_em(symbol=code, indicator="累计净值走势")
        series = _daily_close_returns(
            data,
            date_column="净值日期",
            value_column="累计净值",
        )
        frame = _merge_returns(frame, key, series, start=start, through=through)
        refreshed.append(key)

    industries = pro.index_classify(level="L1", src="SW2021")
    industry_codes = dict(
        zip(industries["industry_name"], industries["index_code"], strict=True)
    )
    for name in frame["申万一级行业"].columns:
        ts_code = industry_codes[name]
        data = pro.sw_daily(
            ts_code=ts_code,
            start_date=fetch_start,
            end_date=fetch_end,
        )
        series = _daily_close_returns(
            data,
            date_column="trade_date",
            value_column="close",
        )
        key = ("申万一级行业", name)
        frame = _merge_returns(frame, key, series, start=start, through=through)
        refreshed.append(key)

    for key, symbol in GLOBAL_YAHOO_SPECS.items():
        series = _yahoo_monthly(symbol, start=start, through=through)
        frame = _merge_returns(frame, key, series, start=start, through=through)
        refreshed.append(key)

    panel = pd.read_parquet(PANEL_PATH)
    panel.index = pd.to_datetime(panel.index)
    for key, column in LOCAL_PANEL_SPECS.items():
        series = _monthly_returns(panel[column])
        frame = _merge_returns(frame, key, series, start=start, through=through)
        refreshed.append(key)

    ff17 = _ken_french_17_monthly()
    ff17_source_end = ff17.dropna(how="all").index.max()
    for name in frame[FF17_CATEGORY].columns:
        key = (FF17_CATEGORY, name)
        frame = _merge_returns(
            frame,
            key,
            ff17[name],
            start=frame.index.min(),
            through=through,
        )
        refreshed.append(key)

    refreshed = sorted(set(refreshed))
    coverage = []
    for category in frame.columns.get_level_values(0).unique():
        category_frame = frame[category]
        ends = category_frame.apply(lambda series: series.last_valid_index())
        coverage.append(
            {
                "category": category,
                "assets": int(category_frame.shape[1]),
                "minimumEnd": ends.min().strftime("%Y-%m"),
                "maximumEnd": ends.max().strftime("%Y-%m"),
            }
        )
    return frame.sort_index(), {
        "source": "Tushare Pro + Akshare cumulative NAV + Yahoo adjusted close + Ken French Data Library incremental refresh",
        "start": start.strftime("%Y-%m"),
        "through": through.strftime("%Y-%m"),
        "sourceDataEnd": ff17_source_end.strftime("%Y-%m"),
        "refreshedAssets": len(refreshed),
        "addedAssets": ["||".join(key) for key in missing_columns],
        "coverage": coverage,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", help="Last completed month, for example 2026-06")
    parser.add_argument("--lookback-months", type=int, default=12)
    parser.add_argument(
        "--ff17-only",
        action="store_true",
        help="Refresh the official Ken French 17 industry monthly history only",
    )
    args = parser.parse_args()

    through = _month_end(
        args.through or (pd.Timestamp.today() - pd.offsets.MonthEnd(1))
    )
    start = through - pd.DateOffset(months=args.lookback_months)
    frame = pd.read_parquet(RETURNS_PATH)
    frame.index = pd.to_datetime(frame.index)
    before_end = frame.dropna(how="all").index.max().strftime("%Y-%m")
    if args.ff17_only:
        refreshed, audit = refresh_ff17_returns(frame, through=through)
    else:
        token = os.environ.get("TUSHARE_TOKEN", "").strip()
        if not token:
            raise RuntimeError("TUSHARE_TOKEN is required in the environment")
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        refreshed, audit = refresh_returns(frame, pro, start=start, through=through)
    temporary = RETURNS_PATH.with_suffix(".parquet.tmp")
    refreshed.to_parquet(temporary)
    temporary.replace(RETURNS_PATH)
    payload = {
        "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
        "beforeReturnsEnd": before_end,
        "afterReturnsEnd": refreshed.dropna(how="all").index.max().strftime("%Y-%m"),
        **audit,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
