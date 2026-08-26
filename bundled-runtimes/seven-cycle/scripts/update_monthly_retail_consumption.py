from __future__ import annotations

from pathlib import Path

import akshare as ak
import pandas as pd


def _to_month_end(dates: pd.Series) -> pd.DatetimeIndex:
    dt = pd.to_datetime(dates, errors="coerce")
    return (dt + pd.offsets.MonthEnd(0)).dt.normalize()


def _parse_cn_month(dates: pd.Series) -> pd.DatetimeIndex:
    raw = dates.astype(str)
    raw = raw.str.replace("年", "-", regex=False)
    raw = raw.str.replace("月", "", regex=False)
    raw = raw.str.replace("份", "", regex=False)
    return _to_month_end(raw)


def _series_from_release(df: pd.DataFrame, date_col: str, value_col: str) -> pd.Series:
    series = pd.Series(pd.to_numeric(df[value_col], errors="coerce"), index=_to_month_end(df[date_col]))
    series = series.groupby(level=0).last()
    return series


def _series_from_cn(df: pd.DataFrame, value_col: str) -> pd.Series:
    series = pd.Series(pd.to_numeric(df[value_col], errors="coerce"), index=_parse_cn_month(df["月份"]))
    series = series.groupby(level=0).last()
    return series


def main() -> None:
    panel_path = Path("data/indicator_panel_monthly.parquet")
    df = pd.read_parquet(panel_path)

    add = {}

    cn_retail = ak.macro_china_consumer_goods_retail()
    add["CN_RETAIL_SALES_LEVEL"] = _series_from_cn(cn_retail, "当月")
    add["CN_RETAIL_SALES_MOM"] = _series_from_cn(cn_retail, "环比增长")
    add["CN_RETAIL_SALES_YOY"] = _series_from_cn(cn_retail, "同比增长")
    add["CN_RETAIL_SALES_CUM_LEVEL"] = _series_from_cn(cn_retail, "累计")
    add["CN_RETAIL_SALES_CUM_YOY"] = _series_from_cn(cn_retail, "累计-同比增长")

    add["US_RETAIL_SALES_MOM"] = _series_from_release(ak.macro_usa_retail_sales(), "日期", "今值")
    add["EU_RETAIL_SALES_MOM"] = _series_from_release(ak.macro_euro_retail_sales_mom(), "日期", "今值")

    add["DE_RETAIL_SALES_MOM"] = _series_from_release(ak.macro_germany_retail_sale_monthly(), "时间", "现值")
    add["DE_RETAIL_SALES_YOY"] = _series_from_release(ak.macro_germany_retail_sale_yearly(), "时间", "现值")
    add["UK_RETAIL_SALES_MOM"] = _series_from_release(ak.macro_uk_retail_monthly(), "时间", "现值")
    add["UK_RETAIL_SALES_YOY"] = _series_from_release(ak.macro_uk_retail_yearly(), "时间", "现值")
    add["AU_RETAIL_SALES_MOM"] = _series_from_release(ak.macro_australia_retail_rate_monthly(), "时间", "现值")
    add["CA_RETAIL_SALES_MOM"] = _series_from_release(ak.macro_canada_retail_rate_monthly(), "时间", "现值")

    add["US_CONSUMER_CONFIDENCE_LEVEL"] = _series_from_release(
        ak.macro_usa_cb_consumer_confidence(), "日期", "今值"
    )
    add["US_CONSUMER_SENTIMENT_LEVEL"] = _series_from_release(
        ak.macro_usa_michigan_consumer_sentiment(), "日期", "今值"
    )

    new_df = pd.DataFrame(add)
    df = df.join(new_df, how="outer")
    df = df.sort_index()
    df.to_parquet(panel_path)

    added_cols = [col for col in add.keys() if col in df.columns]
    print(f"Added {len(added_cols)} retail/consumption columns.")
    print("Columns:")
    for col in added_cols:
        print(f"- {col}")


if __name__ == "__main__":
    main()
