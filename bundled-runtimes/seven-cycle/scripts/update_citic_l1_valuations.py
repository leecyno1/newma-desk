from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import tushare as ts



_CITIC_L1 = {
    "CI005001": "石油石化",
    "CI005002": "煤炭",
    "CI005003": "有色金属",
    "CI005004": "电力及公用事业",
    "CI005005": "钢铁",
    "CI005006": "基础化工",
    "CI005007": "建筑",
    "CI005008": "建材",
    "CI005009": "轻工制造",
    "CI005010": "机械",
    "CI005011": "电力设备及新能源",
    "CI005012": "国防军工",
    "CI005013": "汽车",
    "CI005014": "商贸零售",
    "CI005015": "消费者服务",
    "CI005016": "家电",
    "CI005017": "纺织服装",
    "CI005018": "医药",
    "CI005019": "食品饮料",
    "CI005020": "农林牧渔",
    "CI005021": "银行",
    "CI005022": "非银行金融",
    "CI005023": "房地产",
    "CI005024": "交通运输",
    "CI005025": "电子",
    "CI005026": "通信",
    "CI005027": "计算机",
    "CI005028": "传媒",
    "CI005029": "综合",
    "CI005030": "综合金融",
}


def _month_end(dates: pd.Series) -> pd.DatetimeIndex:
    dt = pd.to_datetime(dates, errors="coerce")
    return (dt + pd.offsets.MonthEnd(0)).dt.normalize()


def _extract_citic_l1_codes(columns: list[str]) -> list[str]:
    pattern = re.compile(r"IDX_CITIC_L1_(CI\d{6})_CI_LEVEL")
    return sorted({match.group(1) for col in columns if (match := pattern.match(col))})


def _map_industry_to_citic(industry: str) -> str | None:
    if not industry:
        return None
    text = str(industry)
    rules = [
        ("银行", "CI005021"),
        ("保险", "CI005022"),
        ("证券", "CI005022"),
        ("信托", "CI005022"),
        ("多元金融", "CI005030"),
        ("综合金融", "CI005030"),
        ("房地产", "CI005023"),
        ("地产", "CI005023"),
        ("煤炭", "CI005002"),
        ("钢铁", "CI005005"),
        ("普钢", "CI005005"),
        ("特种钢", "CI005005"),
        ("钢加工", "CI005005"),
        ("有色", "CI005003"),
        ("小金属", "CI005003"),
        ("石油", "CI005001"),
        ("油气", "CI005001"),
        ("化工", "CI005006"),
        ("电力", "CI005004"),
        ("公用", "CI005004"),
        ("建筑", "CI005007"),
        ("建材", "CI005008"),
        ("轻工", "CI005009"),
        ("机械", "CI005010"),
        ("电气设备", "CI005011"),
        ("新能源", "CI005011"),
        ("军工", "CI005012"),
        ("国防", "CI005012"),
        ("航空", "CI005012"),
        ("航天", "CI005012"),
        ("船舶", "CI005012"),
        ("汽车", "CI005013"),
        ("商贸", "CI005014"),
        ("零售", "CI005014"),
        ("酒店", "CI005015"),
        ("旅游", "CI005015"),
        ("餐饮", "CI005015"),
        ("景点", "CI005015"),
        ("家用电器", "CI005016"),
        ("家电", "CI005016"),
        ("纺织", "CI005017"),
        ("服装", "CI005017"),
        ("医药", "CI005018"),
        ("生物", "CI005018"),
        ("食品", "CI005019"),
        ("饮料", "CI005019"),
        ("酒", "CI005019"),
        ("农业", "CI005020"),
        ("林业", "CI005020"),
        ("牧业", "CI005020"),
        ("渔业", "CI005020"),
        ("交通运输", "CI005024"),
        ("港口", "CI005024"),
        ("航运", "CI005024"),
        ("航空", "CI005024"),
        ("公路", "CI005024"),
        ("铁路", "CI005024"),
        ("物流", "CI005024"),
        ("电子", "CI005025"),
        ("半导体", "CI005025"),
        ("元器件", "CI005025"),
        ("通信", "CI005026"),
        ("计算机", "CI005027"),
        ("软件", "CI005027"),
        ("传媒", "CI005028"),
        ("文化", "CI005028"),
        ("出版", "CI005028"),
        ("广告", "CI005028"),
        ("综合", "CI005029"),
    ]
    for keyword, code in rules:
        if keyword in text:
            return code
    return None


def main() -> None:
    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "TUSHARE_TOKEN is required; set it in the environment "
            "before running this script"
        )
    ts.set_token(token)
    pro = ts.pro_api()

    panel_path = Path("data/indicator_panel_monthly.parquet")
    df = pd.read_parquet(panel_path)

    codes = _extract_citic_l1_codes(list(df.columns))
    if not codes:
        raise RuntimeError("No CITIC L1 index columns found in monthly panel.")

    stock_basic = pro.stock_basic(exchange="", list_status="L", fields="ts_code,industry")
    stock_basic["citic_code"] = stock_basic["industry"].apply(_map_industry_to_citic)
    stock_basic = stock_basic.dropna(subset=["citic_code"])

    min_date = df.index.min()
    max_date = df.index.max()
    start_date = min_date.strftime("%Y%m%d") if hasattr(min_date, "strftime") else "20100101"
    end_date = max_date.strftime("%Y%m%d") if hasattr(max_date, "strftime") else ""

    cal = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date, is_open="1")
    if cal.empty:
        raise RuntimeError("Trade calendar not available from Tushare.")
    cal["cal_date"] = pd.to_datetime(cal["cal_date"], format="%Y%m%d", errors="coerce")
    cal = cal.dropna(subset=["cal_date"])
    cal["month"] = cal["cal_date"].dt.to_period("M")
    month_end_dates = cal.groupby("month")["cal_date"].max().dt.strftime("%Y%m%d").tolist()

    added = {}
    for trade_date in month_end_dates:
        daily = pro.daily_basic(
            trade_date=trade_date,
            fields="ts_code,trade_date,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,total_mv",
        )
        if daily.empty:
            continue
        daily = daily.merge(stock_basic[["ts_code", "citic_code"]], on="ts_code", how="inner")
        if daily.empty:
            continue
        daily = daily.copy()
        daily["pe"] = pd.to_numeric(daily["pe"], errors="coerce")
        daily["pb"] = pd.to_numeric(daily["pb"], errors="coerce")
        daily["ps"] = pd.to_numeric(daily["ps"], errors="coerce")
        daily["dv_ratio"] = pd.to_numeric(daily["dv_ratio"], errors="coerce")
        daily["total_mv"] = pd.to_numeric(daily["total_mv"], errors="coerce")
        daily["roe_proxy"] = daily["pb"] / daily["pe"]

        grouped = daily.groupby("citic_code")
        for citic_code, group in grouped:
            if citic_code not in codes:
                continue
            weights = group["total_mv"]
            if weights.isna().all():
                continue
            def _wavg(series: pd.Series) -> float | None:
                mask = series.notna() & weights.notna()
                if not mask.any():
                    return None
                return (series[mask] * weights[mask]).sum() / weights[mask].sum()

            prefix = f"IDX_CITIC_L1_{citic_code}_CI"
            added.setdefault(f"{prefix}_PE", {})[trade_date] = _wavg(group["pe"])
            added.setdefault(f"{prefix}_PB", {})[trade_date] = _wavg(group["pb"])
            added.setdefault(f"{prefix}_PS", {})[trade_date] = _wavg(group["ps"])
            added.setdefault(f"{prefix}_DIV_YIELD", {})[trade_date] = _wavg(group["dv_ratio"])
            added.setdefault(f"{prefix}_ROE", {})[trade_date] = _wavg(group["roe_proxy"])

    if not added:
        raise RuntimeError("No CITIC L1 valuation series derived from daily_basic.")

    new_df = pd.DataFrame(added)
    new_df.index = pd.to_datetime(new_df.index, format="%Y%m%d", errors="coerce")
    new_df = new_df.dropna(axis=0, how="all")
    new_df = new_df.sort_index()
    overlap = [col for col in new_df.columns if col in df.columns]
    if overlap:
        df = df.drop(columns=overlap)
    df = df.join(new_df, how="outer")
    df = df.sort_index()
    df.to_parquet(panel_path)

    added_cols = sorted(added.keys())
    print(f"Added {len(added_cols)} CITIC L1 valuation columns.")
    for col in added_cols:
        print(f"- {col}")


if __name__ == "__main__":
    main()
