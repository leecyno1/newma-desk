"""Incrementally refresh current C5/C7 research inputs with Tushare Pro.

The updater only overwrites explicitly mapped columns and dates. It does not
rebuild the full 1,800-column panel, so unavailable sources cannot erase the
approved long-history data already stored in the panel.
"""

from __future__ import annotations

from pathlib import Path
import argparse
from datetime import date
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_monthly.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "research_current_panel_refresh.json"

INDEX_SPECS = {
    "IDX_SH_COMP": "000001.SH",
    "IDX_SZ_COMP": "399001.SZ",
    "IDX_HS300": "000300.SH",
    "IDX_CSI500": "000905.SH",
    "IDX_GEM": "399006.SZ",
    "IDX_CSI300_HIGH_BETA": "000828.CSI",
    "IDX_CSI300R_GROWTH": "000918.CSI",
    "IDX_CSI300R_VALUE": "000919.CSI",
    "IDX_CSI300_LOW_BETA": "000829.CSI",
    "IDX_CSI300_VOL": "000803.CSI",
    "IDX_CSI500_DIVIDEND": "000822.CSI",
    "IDX_CSI500_HIGH_BETA": "000830.CSI",
    "IDX_CSI500_LOW_BETA": "000831.CSI",
    "IDX_CSI500_VOL": "000804.CSI",
    "IDX_CSI_DIV_LOWVOL": "h30269.CSI",
}

TURNOVER_SPECS = {
    key: INDEX_SPECS[key]
    for key in ("IDX_SH_COMP", "IDX_SZ_COMP", "IDX_HS300", "IDX_CSI500", "IDX_GEM")
}

PMI_PROXY_SPECS = {
    "PMI010402": "PMI010400",
    "PMI010403": "PMI010400",
    "PMI010502": "PMI010500",
    "PMI010503": "PMI010500",
    "PMI010601": "PMI010600",
    "PMI010602": "PMI010600",
    "PMI010603": "PMI010600",
    "PMI010701": "PMI010700",
}
PMI_DIRECT_HISTORY_MONTHS = 180

COMEX_GOLD_PREFIX = "US_COMEX_GOLD_FUT"
COMMODITY_PRICE_PREFIX = "CN_COMMODITY_PRICE_INDEX_AK"
FRED_SPECS = {
    "US_FEDFUNDS": ("FEDFUNDS", "last", "diff"),
    "US_BROAD_DOLLAR": ("DTWEXBGS", "mean", "pct"),
    "US_FED_BALANCE_SHEET": ("WALCL", "last", "pct"),
    "US_NFCI": ("NFCI", "mean", "diff"),
}


def _month_end(value: str | pd.Timestamp | date) -> pd.Timestamp:
    return pd.Timestamp(value).to_period("M").to_timestamp("M")


def _pmi_history_start(
    start: pd.Timestamp,
    through: pd.Timestamp,
) -> pd.Timestamp:
    return min(start, through - pd.DateOffset(months=PMI_DIRECT_HISTORY_MONTHS))


def _monthly_last(
    frame: pd.DataFrame,
    date_column: str,
    value_column: str,
) -> pd.Series:
    dates = pd.to_datetime(frame[date_column].astype(str), errors="coerce")
    values = pd.to_numeric(frame[value_column], errors="coerce")
    series = pd.Series(values.to_numpy(), index=dates).dropna().sort_index()
    return series.resample("ME").last()


def _commodity_price_monthly(frame: pd.DataFrame) -> pd.Series:
    return _monthly_last(frame, "日期", "最新值")


def _ensure_index(panel: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    return panel.reindex(panel.index.union(index).sort_values())


def _normalize_monthly_panel(panel: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    normalized = panel.copy()
    normalized.index = (
        pd.DatetimeIndex(normalized.index).to_period("M").to_timestamp("M")
    )
    duplicate_rows = int(normalized.index.duplicated().sum())
    if duplicate_rows:
        normalized = normalized.sort_index().groupby(level=0, sort=True).last()
    return normalized.sort_index(), duplicate_rows


def _merge_level_variants(
    panel: pd.DataFrame,
    prefix: str,
    level: pd.Series,
    *,
    change_mode: str,
) -> pd.DataFrame:
    level = pd.to_numeric(level, errors="coerce").dropna().sort_index()
    if level.empty:
        return panel
    panel = _ensure_index(panel, pd.DatetimeIndex(level.index))
    level_column = f"{prefix}_LEVEL"
    panel.loc[level.index, level_column] = level.to_numpy()
    combined = pd.to_numeric(panel[level_column], errors="coerce")
    if change_mode == "diff":
        month_change = combined.diff()
        year_change = combined.diff(12)
    elif change_mode == "pct":
        month_change = combined.pct_change(fill_method=None)
        year_change = combined.pct_change(12, fill_method=None)
    else:
        raise ValueError(f"Unsupported change mode: {change_mode}")
    panel.loc[level.index, f"{prefix}_MOM"] = month_change.reindex(
        level.index
    ).to_numpy()
    panel.loc[level.index, f"{prefix}_YOY"] = year_change.reindex(
        level.index
    ).to_numpy()
    return panel


def _merge_direct(
    panel: pd.DataFrame,
    column: str,
    series: pd.Series,
) -> pd.DataFrame:
    series = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if series.empty:
        return panel
    panel = _ensure_index(panel, pd.DatetimeIndex(series.index))
    panel.loc[series.index, column] = series.to_numpy()
    return panel


def _coverage(panel: pd.DataFrame, columns: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for column in columns:
        series = pd.to_numeric(panel[column], errors="coerce").dropna()
        rows.append(
            {
                "column": column,
                "start": series.index.min().strftime("%Y-%m")
                if not series.empty
                else None,
                "end": series.index.max().strftime("%Y-%m")
                if not series.empty
                else None,
                "observations": int(len(series)),
            }
        )
    return rows


def _yahoo_monthly_level(
    symbol: str,
    *,
    start: pd.Timestamp,
    through: pd.Timestamp,
) -> pd.Series:
    query = urlencode(
        {
            "period1": int(start.timestamp()),
            "period2": int((through + pd.Timedelta(days=1)).timestamp()),
            "interval": "1mo",
            "events": "history",
        }
    )
    request = Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(f"Yahoo Finance error for {symbol}: {chart['error']}")
    results = chart.get("result") or []
    if not results:
        raise RuntimeError(f"Yahoo Finance returned no result for {symbol}")
    result = results[0]
    timestamps = pd.to_datetime(result.get("timestamp", []), unit="s", utc=True)
    quotes = result.get("indicators", {}).get("quote") or []
    if not quotes:
        raise RuntimeError(f"Yahoo Finance returned no quote data for {symbol}")
    closes = pd.to_numeric(pd.Series(quotes[0].get("close", [])), errors="coerce")
    if len(timestamps) != len(closes):
        raise RuntimeError(f"Yahoo Finance returned inconsistent data for {symbol}")
    index = timestamps.tz_convert(None).to_period("M").to_timestamp("M")
    series = pd.Series(closes.to_numpy(), index=index).dropna().sort_index()
    return series.groupby(level=0).last().loc[:through]


def _fred_monthly_level(
    series_id: str,
    *,
    start: pd.Timestamp,
    through: pd.Timestamp,
    aggregation: str,
) -> pd.Series:
    if aggregation not in {"mean", "last"}:
        raise ValueError(f"Unsupported FRED aggregation: {aggregation}")
    query = urlencode(
        {
            "id": series_id,
            "cosd": start.strftime("%Y-%m-%d"),
            "coed": through.strftime("%Y-%m-%d"),
        }
    )
    frame = pd.read_csv(
        f"https://fred.stlouisfed.org/graph/fredgraph.csv?{query}"
    )
    dates = pd.to_datetime(frame.iloc[:, 0], errors="coerce")
    values = pd.to_numeric(frame.iloc[:, 1], errors="coerce")
    series = pd.Series(values.to_numpy(), index=dates).dropna().sort_index()
    series = series.loc[(series.index >= start) & (series.index <= through)]
    if aggregation == "mean":
        return series.resample("ME").mean()
    if aggregation == "last":
        return series.resample("ME").last()
    raise AssertionError("unreachable")


def _repo_r007_monthly(
    pro: object,
    *,
    start: pd.Timestamp,
    through: pd.Timestamp,
) -> pd.Series:
    frames: list[pd.DataFrame] = []
    chunk_start = start
    while chunk_start <= through:
        chunk_end = min(chunk_start + pd.DateOffset(years=4) - pd.Timedelta(days=1), through)
        frame = pro.repo_daily(
            ts_code="206007.SH",
            start_date=chunk_start.strftime("%Y%m%d"),
            end_date=chunk_end.strftime("%Y%m%d"),
        )
        if not frame.empty:
            frames.append(frame)
        chunk_start = chunk_end + pd.Timedelta(days=1)
    if not frames:
        return pd.Series(dtype=float)
    frame = pd.concat(frames, ignore_index=True)
    dates = pd.to_datetime(frame["trade_date"].astype(str), errors="coerce")
    rates = pd.to_numeric(frame["weight"], errors="coerce").fillna(
        pd.to_numeric(frame["close"], errors="coerce")
    )
    series = pd.Series(rates.to_numpy(), index=dates).dropna().sort_index()
    return series.resample("ME").mean().loc[:through]


def _linear_proxy_extension(
    panel: pd.DataFrame,
    *,
    target_column: str,
    parent_column: str,
    direct_end: pd.Timestamp,
    through: pd.Timestamp,
    min_observations: int = 36,
) -> tuple[pd.DataFrame, dict[str, object] | None]:
    overlap = pd.concat(
        [
            pd.to_numeric(panel[target_column], errors="coerce").rename("target"),
            pd.to_numeric(panel[parent_column], errors="coerce").rename("parent"),
        ],
        axis=1,
    ).loc[:direct_end].dropna()
    if len(overlap) < min_observations:
        return panel, None
    design = np.column_stack(
        [np.ones(len(overlap), dtype=float), overlap["parent"].to_numpy(dtype=float)]
    )
    target = overlap["target"].to_numpy(dtype=float)
    intercept, beta = np.linalg.lstsq(design, target, rcond=None)[0]
    fitted = intercept + beta * overlap["parent"].to_numpy(dtype=float)
    residual_sum = float(np.square(target - fitted).sum())
    total_sum = float(np.square(target - target.mean()).sum())
    r2 = 0.0 if total_sum <= 0.0 else 1.0 - residual_sum / total_sum

    target_series = pd.to_numeric(panel[target_column], errors="coerce")
    parent_series = pd.to_numeric(panel[parent_column], errors="coerce")
    candidate_index = parent_series.loc[
        (parent_series.index > direct_end) & (parent_series.index <= through)
    ].dropna().index
    missing_index = candidate_index[target_series.reindex(candidate_index).isna()]
    if not missing_index.empty:
        proxy_values = intercept + beta * parent_series.loc[missing_index]
        prefix = target_column.removesuffix("_LEVEL")
        panel = _merge_level_variants(panel, prefix, proxy_values, change_mode="diff")
    proxy_index = candidate_index[
        pd.to_numeric(panel[target_column], errors="coerce")
        .reindex(candidate_index)
        .notna()
    ]
    if proxy_index.empty:
        return panel, None
    return panel, {
        "column": target_column,
        "proxyFor": parent_column,
        "fitStart": overlap.index.min().strftime("%Y-%m"),
        "fitEnd": overlap.index.max().strftime("%Y-%m"),
        "directThrough": direct_end.strftime("%Y-%m"),
        "proxyStart": proxy_index.min().strftime("%Y-%m"),
        "proxyEnd": proxy_index.max().strftime("%Y-%m"),
        "proxyObservations": int(len(proxy_index)),
        "r2": round(float(r2), 6),
        "intercept": round(float(intercept), 6),
        "beta": round(float(beta), 6),
        "method": "tail-only OLS: target PMI sub-index = intercept + beta * parent PMI",
        "identity": "explicit_statistical_proxy",
    }


def refresh_panel(
    panel: pd.DataFrame,
    pro: object,
    *,
    start: pd.Timestamp,
    through: pd.Timestamp,
    comex_gold: pd.Series | None = None,
    commodity_price: pd.Series | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    start_date = start.strftime("%Y%m%d")
    end_date = through.strftime("%Y%m%d")
    updated_columns: list[str] = []

    for prefix, ts_code in INDEX_SPECS.items():
        frame = pro.index_daily(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        level = _monthly_last(frame, "trade_date", "close").loc[:through]
        panel = _merge_level_variants(panel, prefix, level, change_mode="pct")
        updated_columns.extend([f"{prefix}_LEVEL", f"{prefix}_MOM", f"{prefix}_YOY"])

    for prefix, ts_code in TURNOVER_SPECS.items():
        frame = pro.index_dailybasic(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )
        for field, suffix in (
            ("turnover_rate", "TURNOVER_RATE"),
            ("turnover_rate_f", "TURNOVER_RATE_F"),
        ):
            level = _monthly_last(frame, "trade_date", field).loc[:through]
            column_prefix = f"{prefix}_{suffix}"
            panel = _merge_level_variants(
                panel,
                column_prefix,
                level,
                change_mode="diff",
            )
            updated_columns.extend(
                [
                    f"{column_prefix}_LEVEL",
                    f"{column_prefix}_MOM",
                    f"{column_prefix}_YOY",
                ]
            )

    margin = pro.margin(start_date=start_date, end_date=end_date)
    margin["trade_date"] = pd.to_datetime(margin["trade_date"].astype(str))
    for exchange, prefix in (
        ("SSE", "CN_MARGIN_SH_FIN_AK"),
        ("SZSE", "CN_MARGIN_SZ_FIN_AK"),
    ):
        exchange_rows = margin.loc[margin["exchange_id"].eq(exchange)]
        level = _monthly_last(exchange_rows, "trade_date", "rzye").loc[:through]
        panel = _merge_level_variants(panel, prefix, level, change_mode="pct")
        updated_columns.extend([f"{prefix}_LEVEL", f"{prefix}_MOM", f"{prefix}_YOY"])

    money = pro.cn_m(start_m=start.strftime("%Y%m"), end_m=through.strftime("%Y%m"))
    money_index = (
        pd.to_datetime(money["month"], format="%Y%m")
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )
    money = money.set_axis(money_index)
    for field, prefix in (("m1", "CN_M_M1"), ("m2", "CN_M_M2")):
        for source_field, suffix in (
            (field, "LEVEL"),
            (f"{field}_mom", "MOM"),
            (f"{field}_yoy", "YOY"),
        ):
            column = f"{prefix}_{suffix}"
            panel = _merge_direct(panel, column, money[source_field].loc[:through])
            updated_columns.append(column)

    social_financing = pro.sf_month(start_m="200201", end_m=through.strftime("%Y%m"))
    social_index = (
        pd.to_datetime(social_financing["month"].astype(str), format="%Y%m")
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )
    social_financing = social_financing.set_axis(social_index).sort_index()
    social_stock = pd.to_numeric(
        social_financing["stk_endval"], errors="coerce"
    ).dropna()
    social_flow_12m = pd.to_numeric(
        social_financing["inc_month"], errors="coerce"
    ).rolling(12, min_periods=12).sum().dropna()
    panel = _merge_level_variants(
        panel,
        "CN_SF_STOCK",
        social_stock.loc[:through],
        change_mode="pct",
    )
    panel = _merge_level_variants(
        panel,
        "CN_SF_FLOW12",
        social_flow_12m.loc[:through],
        change_mode="pct",
    )
    updated_columns.extend(
        [
            "CN_SF_STOCK_LEVEL",
            "CN_SF_STOCK_MOM",
            "CN_SF_STOCK_YOY",
            "CN_SF_FLOW12_LEVEL",
            "CN_SF_FLOW12_MOM",
            "CN_SF_FLOW12_YOY",
        ]
    )

    pmi_start = _pmi_history_start(start, through)
    pmi = pro.cn_pmi(
        start_m=pmi_start.strftime("%Y%m"),
        end_m=through.strftime("%Y%m"),
    )
    pmi.columns = [str(column).upper() for column in pmi.columns]
    pmi_index = (
        pd.to_datetime(pmi["MONTH"].astype(str), format="%Y%m")
        .dt.to_period("M")
        .dt.to_timestamp("M")
    )
    pmi = pmi.set_axis(pmi_index).sort_index()
    direct_pmi_ends: dict[str, pd.Timestamp] = {}
    for field in sorted(column for column in pmi.columns if column.startswith("PMI")):
        prefix = f"CN_PMI_{field}"
        if f"{prefix}_LEVEL" not in panel.columns:
            continue
        level = pd.to_numeric(pmi[field], errors="coerce").dropna().loc[:through]
        if level.empty:
            continue
        panel = _merge_level_variants(panel, prefix, level, change_mode="diff")
        direct_pmi_ends[field] = pd.Timestamp(level.index.max())
        updated_columns.extend([f"{prefix}_LEVEL", f"{prefix}_MOM", f"{prefix}_YOY"])

    shibor = pro.shibor(start_date=start_date, end_date=end_date)
    for field, prefix in (("on", "CN_SHIBOR_ON_AK"), ("3m", "CN_SHIBOR_3M")):
        level = _monthly_last(shibor, "date", field).loc[:through]
        panel = _merge_level_variants(panel, prefix, level, change_mode="diff")
        updated_columns.extend([f"{prefix}_LEVEL", f"{prefix}_MOM", f"{prefix}_YOY"])

    lpr = pro.shibor_lpr(start_date=start_date, end_date=end_date)
    for field, prefix in (("1y", "CN_LPR_1Y_AK"), ("5y", "CN_LPR_5Y_AK")):
        level = _monthly_last(lpr, "date", field).loc[:through]
        panel = _merge_level_variants(panel, prefix, level, change_mode="diff")
        updated_columns.extend([f"{prefix}_LEVEL", f"{prefix}_MOM", f"{prefix}_YOY"])

    repo_r007 = _repo_r007_monthly(
        pro,
        start=pd.Timestamp("2006-10-01"),
        through=through,
    )
    panel = _merge_level_variants(
        panel,
        "CN_REPO_R007",
        repo_r007,
        change_mode="diff",
    )
    updated_columns.extend(
        ["CN_REPO_R007_LEVEL", "CN_REPO_R007_MOM", "CN_REPO_R007_YOY"]
    )

    fred_start = pd.Timestamp("2000-01-01")
    for prefix, (series_id, aggregation, change_mode) in FRED_SPECS.items():
        level = _fred_monthly_level(
            series_id,
            start=fred_start,
            through=through,
            aggregation=aggregation,
        )
        panel = _merge_level_variants(
            panel,
            prefix,
            level,
            change_mode=change_mode,
        )
        updated_columns.extend(
            [f"{prefix}_LEVEL", f"{prefix}_MOM", f"{prefix}_YOY"]
        )

    proxy_columns: list[dict[str, object]] = []
    for target_field, parent_field in PMI_PROXY_SPECS.items():
        direct_end = direct_pmi_ends.get(target_field)
        if direct_end is None or direct_end >= through:
            continue
        target_column = f"CN_PMI_{target_field}_LEVEL"
        parent_column = f"CN_PMI_{parent_field}_LEVEL"
        panel, proxy_audit = _linear_proxy_extension(
            panel,
            target_column=target_column,
            parent_column=parent_column,
            direct_end=direct_end,
            through=through,
        )
        if proxy_audit is not None:
            proxy_columns.append(proxy_audit)
            prefix = target_column.removesuffix("_LEVEL")
            updated_columns.extend([f"{prefix}_LEVEL", f"{prefix}_MOM", f"{prefix}_YOY"])

    if comex_gold is not None and not comex_gold.dropna().empty:
        panel = _merge_level_variants(
            panel,
            COMEX_GOLD_PREFIX,
            comex_gold.loc[:through],
            change_mode="pct",
        )
        updated_columns.extend(
            [
                f"{COMEX_GOLD_PREFIX}_LEVEL",
                f"{COMEX_GOLD_PREFIX}_MOM",
                f"{COMEX_GOLD_PREFIX}_YOY",
            ]
        )

    if commodity_price is not None and not commodity_price.dropna().empty:
        panel = _merge_level_variants(
            panel,
            COMMODITY_PRICE_PREFIX,
            commodity_price.loc[:through],
            change_mode="pct",
        )
        updated_columns.extend(
            [
                f"{COMMODITY_PRICE_PREFIX}_LEVEL",
                f"{COMMODITY_PRICE_PREFIX}_MOM",
                f"{COMMODITY_PRICE_PREFIX}_YOY",
            ]
        )

    updated_columns = sorted(set(updated_columns))
    return panel.sort_index(), {
        "source": "Tushare Pro + FRED + Yahoo Finance + AkShare incremental refresh",
        "start": start.strftime("%Y-%m"),
        "through": through.strftime("%Y-%m"),
        "updatedColumnCount": len(updated_columns),
        "proxyColumns": proxy_columns,
        "coverage": _coverage(panel, updated_columns),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", help="Last completed month, for example 2026-06")
    parser.add_argument("--lookback-months", type=int, default=18)
    args = parser.parse_args()

    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is required in the environment")
    through = _month_end(
        args.through or (pd.Timestamp.today() - pd.offsets.MonthEnd(1))
    )
    start = through - pd.DateOffset(months=args.lookback_months)

    import tushare as ts

    ts.set_token(token)
    pro = ts.pro_api()
    comex_gold = _yahoo_monthly_level("GC=F", start=start, through=through)
    import akshare as ak

    commodity_price = _commodity_price_monthly(
        ak.macro_china_commodity_price_index()
    ).loc[:through]
    panel = pd.read_parquet(PANEL_PATH)
    panel, coalesced_duplicate_month_rows = _normalize_monthly_panel(panel)
    before_end = panel.dropna(how="all").index.max().strftime("%Y-%m")
    refreshed, audit = refresh_panel(
        panel,
        pro,
        start=start,
        through=through,
        comex_gold=comex_gold,
        commodity_price=commodity_price,
    )
    temporary = PANEL_PATH.with_suffix(".parquet.tmp")
    refreshed.to_parquet(temporary)
    temporary.replace(PANEL_PATH)
    payload = {
        "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
        "beforePanelEnd": before_end,
        "afterPanelEnd": refreshed.dropna(how="all").index.max().strftime("%Y-%m"),
        "coalescedDuplicateMonthRows": coalesced_duplicate_month_rows,
        **audit,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
