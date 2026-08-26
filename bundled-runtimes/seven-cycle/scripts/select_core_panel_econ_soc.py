"""
Select a compact core indicator set using an economics + sociology framework.

Outputs:
- output/core_panel_core_set.csv
- output/core_panel_core_set.md
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd


HUATAI_CATEGORIES = [
    "股指",
    "股指财务",
    "行业指数",
    "行业指数财务",
    "利率",
    "商品",
    "汇率",
    "CPI",
    "PPI",
    "制造业PMI",
    "服务业PMI",
    "货币供给",
    "工业生产",
    "零售消费",
]

# Monthly quality gate for core dashboard:
# - remove all-empty series
# - remove series with too few valid observations (too noisy for cycle studies)
MONTHLY_MIN_OBS = 60


def _category_from_col(col: str) -> str:
    if col.startswith("DERIVED_"):
        return "Derived"
    if col.startswith("WB_"):
        return "WorldBank"
    if col.startswith("MPD_"):
        return "MPD"
    if col.startswith("UK_BOE_"):
        return "BoE"
    if col.startswith("UK_OECD_") or col.startswith("EA_OECD_") or col.endswith("_OECD"):
        return "OECD"
    if col.startswith("US_SHILLER_"):
        return "Shiller"
    if col.startswith("US_FF"):
        return "US/FF"
    if col.startswith("CN_"):
        return "China"
    if col.startswith("IDX_") or col.startswith("ETF_"):
        return "China/Market"
    if col.startswith("US_") or col.startswith("EU_") or col.startswith("JP_") or col.startswith("DXY") or col.startswith("GOLD"):
        return "Global"
    return "Other"


def _pick_first_available(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


CORE_COUNTRIES = [
    ("USA", "美国"),
    ("CHN", "中国"),
    ("JPN", "日本"),
    ("DEU", "德国"),
    ("GBR", "英国"),
    ("FRA", "法国"),
    ("ITA", "意大利"),
    ("ESP", "西班牙"),
    ("NLD", "荷兰"),
    ("IND", "印度"),
    ("BRA", "巴西"),
    ("CAN", "加拿大"),
    ("KOR", "韩国"),
    ("AUS", "澳大利亚"),
    ("RUS", "俄罗斯"),
    ("MEX", "墨西哥"),
]


def _gdp_weighted_series(df: pd.DataFrame, value_cols: list[str], weight_cols: list[str]) -> pd.Series:
    values = df[value_cols].to_numpy(dtype="float64")
    weights = df[weight_cols].to_numpy(dtype="float64")
    mask = ~np.isnan(values) & ~np.isnan(weights)
    numerator = np.nansum(values * weights * mask, axis=1)
    denominator = np.nansum(weights * mask, axis=1)
    series = numerator / denominator
    return pd.Series(series, index=df.index)


def _huatai_category_from_col(col: str, dimension: str | None = None) -> str:
    upper = col.upper()
    if "CPI" in upper:
        return "CPI"
    if "PPI" in upper:
        return "PPI"
    if "PMI" in upper:
        if (
            "SERV" in upper
            or "SERVICE" in upper
            or "NON_MANUFACTUR" in upper
            or "NONMAN" in upper
            or "PMI02" in upper
            or "PMI020" in upper
            or "PMI03" in upper
        ):
            return "服务业PMI"
        return "制造业PMI"
    if "M0" in upper or "M1" in upper or "M2" in upper or "BROAD_MONEY" in upper:
        if upper.startswith("US_FF"):
            return "行业指数"
        return "货币供给"
    if upper.startswith("US_FF"):
        if "TRAIL12" in upper or "BM_OP" in upper or "ME_OP" in upper:
            return "行业指数财务"
        return "行业指数"
    if upper.startswith("IDX_CITIC_L"):
        if any(
            tag in upper
            for tag in [
                "PE",
                "PB",
                "DIVIDEND",
                "YIELD",
                "PS",
                "PCF",
                "ROE",
                "EPS",
                "BPS",
            ]
        ):
            return "行业指数财务"
        return "行业指数"
    if "IR_" in upper or "HIBOR" in upper or "SHIBOR" in upper:
        return "利率"
    if "YIELD" in upper and "DIV_YIELD" not in upper:
        return "利率"
    if upper.startswith("IDX_") or upper.startswith("US_SPX") or upper.startswith("US_NDX") or upper.startswith("US_DJI"):
        if any(
            tag in upper
            for tag in [
                "PE",
                "PB",
                "DIVIDEND",
                "YIELD",
                "PS",
                "PCF",
                "ROE",
                "EPS",
                "BPS",
            ]
        ):
            return "股指财务"
        return "股指"
    if upper.startswith("EU_STOXX") or upper.startswith("JP_NIKKEI") or upper.startswith("HK_HS"):
        return "股指"
    if upper.startswith("ETF_"):
        if "DIVIDEND" in upper or "YIELD" in upper:
            return "股指财务"
        return "股指"
    if "GOLD" in upper or "OIL" in upper or "WTI" in upper or "BRENT" in upper or "COPPER" in upper:
        return "商品"
    if "COMMOD" in upper or "METAL" in upper:
        return "商品"
    if "DXY" in upper or "EXCHANGE" in upper:
        return "汇率"
    if "INDUSTRIAL" in upper or "IND_PROD" in upper or "_IP_" in upper:
        return "工业生产"
    if "RETAIL" in upper or "CONSUMER" in upper or "CONFIDENCE" in upper or "SENTIMENT" in upper or "SALES" in upper:
        return "零售消费"
    if dimension in {"价格/通胀"}:
        return "CPI"
    return "非华泰"


def _series_span(series: pd.Series) -> tuple[int | None, int | None, float]:
    non_null = series.dropna()
    if non_null.empty:
        return None, None, 100.0
    start = non_null.index.min()
    end = non_null.index.max()
    missing_pct = 100.0 * (series.isna().sum() / len(series))
    if hasattr(start, "year"):
        start = int(start.year)
    if hasattr(end, "year"):
        end = int(end.year)
    return start, end, missing_pct


def main() -> None:
    panel_path = Path("data/indicator_panel_annual_very_long_history_year.parquet")
    monthly_panel_path = Path("data/indicator_panel_monthly.parquet")
    core_path = Path("output/core_panel_selected_tier_modern.csv")
    out_csv = Path("output/core_panel_core_set.csv")
    out_md = Path("output/core_panel_core_set.md")

    df = pd.read_parquet(panel_path)
    if df.index.name != "year":
        df.index = pd.Index(df.index.astype(int), name="year")

    core = pd.read_csv(core_path)
    core_set = set(core.loc[core["tier_modern"] == True, "column"].tolist())
    if "WB_WLD_GOV_REVENUE_PCT_GDP" in df.columns and "WB_WLD_GOV_EXP_PCT_GDP" in df.columns:
        df["DERIVED_WLD_GOV_BALANCE_PCT_GDP"] = (
            df["WB_WLD_GOV_REVENUE_PCT_GDP"] - df["WB_WLD_GOV_EXP_PCT_GDP"]
        )
    gdp_weight_cols = [f"WB_{code}_GDP_CURRENT_USD" for code, _ in CORE_COUNTRIES]
    if all(col in df.columns for col in gdp_weight_cols):
        def _add_weighted(name: str, template: str) -> None:
            value_cols = [template.format(code=code) for code, _ in CORE_COUNTRIES]
            if all(col in df.columns for col in value_cols):
                df[name] = _gdp_weighted_series(df, value_cols, gdp_weight_cols)

        _add_weighted("DERIVED_GDPW_GINI", "WB_{code}_GINI")
        _add_weighted("DERIVED_GDPW_GOV_EFF", "WB_{code}_GOV_GOVERNMENT_EFFECTIVENESS")
        _add_weighted("DERIVED_GDPW_RULE_OF_LAW", "WB_{code}_GOV_RULE_OF_LAW")
        _add_weighted("DERIVED_GDPW_CORRUPTION", "WB_{code}_GOV_CONTROL_OF_CORRUPTION")
        _add_weighted("DERIVED_GDPW_CURRENT_ACCOUNT_PCT_GDP", "WB_{code}_CURRENT_ACCOUNT_PCT_GDP")
        _add_weighted("DERIVED_GDPW_RESERVES_USD", "WB_{code}_TOTAL_RESERVES_USD")
    panel_set = set(df.columns)

    def in_core(cands: list[str]) -> list[str]:
        return [c for c in cands if c in core_set]

    def in_panel(cands: list[str]) -> list[str]:
        return [c for c in cands if c in panel_set and c not in core_set]

    dimensions = [
        {
            "dimension": "宏观增长/生产",
            "items": [
                ("全球GDP(实际, KD)", in_core(["WB_WLD_GDP_REAL_KD"]) + in_panel(["WB_WLD_GDP_REAL_KD"])),
                ("全球GDP增速", in_core(["WB_WLD_GDP_REAL_GROWTH_PCT"]) + in_panel(["WB_WLD_GDP_REAL_GROWTH_PCT"])),
                ("全球人均GDP(实际)", in_core(["WB_WLD_GDP_PC_REAL_KD"]) + in_panel(["WB_WLD_GDP_PC_REAL_KD"])),
                ("美国GDP(实际)", in_core(["WB_USA_GDP_REAL_KD"]) + in_panel(["WB_USA_GDP_REAL_KD"])),
                ("中国GDP(实际)", in_core(["WB_CHN_GDP_REAL_KD"]) + in_panel(["WB_CHN_GDP_REAL_KD"])),
                ("欧盟GDP(实际)", in_core(["WB_EUU_GDP_REAL_KD", "WB_EMU_GDP_REAL_KD"]) + in_panel(["WB_EUU_GDP_REAL_KD", "WB_EMU_GDP_REAL_KD"])),
            ],
        },
        {
            "dimension": "价格/通胀",
            "items": [
                ("全球CPI同比", in_core(["WB_WLD_CPI_YOY_PCT"]) + in_panel(["WB_WLD_CPI_YOY_PCT"])),
                ("美国CPI同比", in_core(["WB_USA_CPI_YOY_PCT", "US_CPI_YOY_OECD_LEVEL"]) + in_panel(["WB_USA_CPI_YOY_PCT", "US_CPI_YOY_OECD_LEVEL"])),
                ("中国CPI同比", in_core(["WB_CHN_CPI_YOY_PCT", "CN_CPI_NT_YOY"]) + in_panel(["WB_CHN_CPI_YOY_PCT", "CN_CPI_NT_YOY"])),
                ("GDP平减指数同比(全球)", in_core(["WB_WLD_GDP_DEFLATOR_YOY_PCT"]) + in_panel(["WB_WLD_GDP_DEFLATOR_YOY_PCT"])),
            ],
        },
        {
            "dimension": "劳动力/就业",
            "items": [
                ("全球失业率", in_core(["WB_WLD_UNEMPLOYMENT_PCT"]) + in_panel(["WB_WLD_UNEMPLOYMENT_PCT"])),
                ("美国失业率", in_core(["WB_USA_UNEMPLOYMENT_PCT", "US_UNRATE_OECD_LEVEL"]) + in_panel(["WB_USA_UNEMPLOYMENT_PCT", "US_UNRATE_OECD_LEVEL"])),
                ("劳参率(全球)", in_core(["WB_WLD_LABOR_FORCE_PARTICIPATION_PCT"]) + in_panel(["WB_WLD_LABOR_FORCE_PARTICIPATION_PCT"])),
            ],
        },
        {
            "dimension": "需求结构",
            "items": [
                ("全球固定资本形成占GDP", in_core(["WB_WLD_GROSS_CAPITAL_FORMATION_PCT_GDP"]) + in_panel(["WB_WLD_GROSS_CAPITAL_FORMATION_PCT_GDP"])),
                ("全球私人消费占GDP", in_core(["WB_WLD_PRIVATE_CONSUMPTION_PCT_GDP"]) + in_panel(["WB_WLD_PRIVATE_CONSUMPTION_PCT_GDP"])),
                ("全球政府消费占GDP", in_core(["WB_WLD_GOVERNMENT_CONSUMPTION_PCT_GDP"]) + in_panel(["WB_WLD_GOVERNMENT_CONSUMPTION_PCT_GDP"])),
                ("全球出口占GDP", in_core(["WB_WLD_EXPORTS_PCT_GDP"]) + in_panel(["WB_WLD_EXPORTS_PCT_GDP"])),
                ("全球进口占GDP", in_core(["WB_WLD_IMPORTS_PCT_GDP"]) + in_panel(["WB_WLD_IMPORTS_PCT_GDP"])),
            ],
        },
        {
            "dimension": "货币/信用",
            "items": [
                ("全球广义货币占GDP", in_core(["WB_WLD_BROAD_MONEY_PCT_GDP"]) + in_panel(["WB_WLD_BROAD_MONEY_PCT_GDP"])),
                ("全球私营部门信贷占GDP", in_core(["WB_WLD_CREDIT_PRIVATE_PCT_GDP"]) + in_panel(["WB_WLD_CREDIT_PRIVATE_PCT_GDP"])),
                ("美国广义货币占GDP", in_core(["WB_USA_BROAD_MONEY_PCT_GDP"]) + in_panel(["WB_USA_BROAD_MONEY_PCT_GDP"])),
                ("中国广义货币占GDP", in_core(["WB_CHN_BROAD_MONEY_PCT_GDP"]) + in_panel(["WB_CHN_BROAD_MONEY_PCT_GDP"])),
            ],
        },
        {
            "dimension": "财政/债务",
            "items": [
                (
                    "发达经济体政府债务占GDP(OECD)",
                    in_core(["WB_OED_GOV_DEBT_PCT_GDP"]) + in_panel(["WB_OED_GOV_DEBT_PCT_GDP"]),
                ),
                (
                    "全球财政余额占GDP(派生)",
                    in_core(["DERIVED_WLD_GOV_BALANCE_PCT_GDP"])
                    + in_panel(["DERIVED_WLD_GOV_BALANCE_PCT_GDP"]),
                ),
                ("全球政府支出占GDP", in_core(["WB_WLD_GOV_EXP_PCT_GDP"]) + in_panel(["WB_WLD_GOV_EXP_PCT_GDP"])),
                ("全球政府收入占GDP", in_core(["WB_WLD_GOV_REVENUE_PCT_GDP"]) + in_panel(["WB_WLD_GOV_REVENUE_PCT_GDP"])),
                ("美国政府债务占GDP", in_core(["WB_USA_GOV_DEBT_PCT_GDP"]) + in_panel(["WB_USA_GOV_DEBT_PCT_GDP"])),
                ("中国政府收入占GDP", in_core(["WB_CHN_GOV_REVENUE_PCT_GDP"]) + in_panel(["WB_CHN_GOV_REVENUE_PCT_GDP"])),
            ],
        },
        {
            "dimension": "外部部门",
            "items": [
                ("全球贸易占GDP", in_core(["WB_WLD_TRADE_PCT_GDP"]) + in_panel(["WB_WLD_TRADE_PCT_GDP"])),
                ("全球FDI净流入占GDP", in_core(["WB_WLD_FDI_NET_INFLOW_PCT_GDP"]) + in_panel(["WB_WLD_FDI_NET_INFLOW_PCT_GDP"])),
                ("外汇储备(月进口)", in_core(["WB_WLD_RESERVES_MONTHS_IMPORTS"]) + in_panel(["WB_WLD_RESERVES_MONTHS_IMPORTS"])),
                (
                    "经常账户占GDP(全球GDP加权)",
                    in_core(["DERIVED_GDPW_CURRENT_ACCOUNT_PCT_GDP"])
                    + in_panel(["DERIVED_GDPW_CURRENT_ACCOUNT_PCT_GDP"]),
                ),
                (
                    "外汇储备(美元, 全球GDP加权)",
                    in_core(["DERIVED_GDPW_RESERVES_USD"]) + in_panel(["DERIVED_GDPW_RESERVES_USD"]),
                ),
                *[
                    (
                        f"经常账户占GDP({name})",
                        in_core([f"WB_{code}_CURRENT_ACCOUNT_PCT_GDP"])
                        + in_panel([f"WB_{code}_CURRENT_ACCOUNT_PCT_GDP"]),
                    )
                    for code, name in CORE_COUNTRIES
                ],
                *[
                    (
                        f"外汇储备(美元)({name})",
                        in_core([f"WB_{code}_TOTAL_RESERVES_USD"])
                        + in_panel([f"WB_{code}_TOTAL_RESERVES_USD"]),
                    )
                    for code, name in CORE_COUNTRIES
                ],
            ],
        },
        {
            "dimension": "人口/社会结构",
            "items": [
                ("全球人口", in_core(["WB_WLD_POPULATION"]) + in_panel(["WB_WLD_POPULATION"])),
                ("全球城镇化率", in_core(["WB_WLD_URBAN_POP_PCT"]) + in_panel(["WB_WLD_URBAN_POP_PCT"])),
                ("预期寿命", in_core(["WB_WLD_LIFE_EXPECTANCY_YEARS"]) + in_panel(["WB_WLD_LIFE_EXPECTANCY_YEARS"])),
                ("成人识字率", in_core(["WB_WLD_ADULT_LITERACY_PCT"]) + in_panel(["WB_WLD_ADULT_LITERACY_PCT"])),
                ("基尼系数(全球GDP加权)", in_core(["DERIVED_GDPW_GINI"]) + in_panel(["DERIVED_GDPW_GINI"])),
                *[
                    (
                        f"基尼系数({name})",
                        in_core([f"WB_{code}_GINI"]) + in_panel([f"WB_{code}_GINI"]),
                    )
                    for code, name in CORE_COUNTRIES
                ],
            ],
        },
        {
            "dimension": "产业结构",
            "items": [
                ("农业增加值占GDP", in_core(["WB_WLD_AGRI_VALUE_ADDED_PCT_GDP"]) + in_panel(["WB_WLD_AGRI_VALUE_ADDED_PCT_GDP"])),
                ("工业增加值占GDP", in_core(["WB_WLD_INDUSTRY_VALUE_ADDED_PCT_GDP"]) + in_panel(["WB_WLD_INDUSTRY_VALUE_ADDED_PCT_GDP"])),
                ("制造业增加值占GDP", in_core(["WB_WLD_MANUFACTURING_VALUE_ADDED_PCT_GDP"]) + in_panel(["WB_WLD_MANUFACTURING_VALUE_ADDED_PCT_GDP"])),
                ("服务业增加值占GDP", in_core(["WB_WLD_SERVICES_VALUE_ADDED_PCT_GDP"]) + in_panel(["WB_WLD_SERVICES_VALUE_ADDED_PCT_GDP"])),
            ],
        },
        {
            "dimension": "能源/环境/资源",
            "items": [
                ("人均能源使用", in_core(["WB_WLD_ENERGY_USE_PER_CAPITA"]) + in_panel(["WB_WLD_ENERGY_USE_PER_CAPITA"])),
                ("人均用电", in_core(["WB_WLD_ELECTRIC_POWER_CONS_PER_CAPITA"]) + in_panel(["WB_WLD_ELECTRIC_POWER_CONS_PER_CAPITA"])),
                ("可再生能源占比", in_core(["WB_WLD_RENEWABLE_ENERGY_CONS_PCT"]) + in_panel(["WB_WLD_RENEWABLE_ENERGY_CONS_PCT"])),
                (
                    "油气煤矿产租金占GDP",
                    in_core(
                        [
                            "WB_WLD_OIL_RENTS_PCT_GDP",
                            "WB_WLD_NATURAL_GAS_RENTS_PCT_GDP",
                            "WB_WLD_COAL_RENTS_PCT_GDP",
                            "WB_WLD_ORES_RENTS_PCT_GDP",
                        ]
                    )
                    + in_panel(
                        [
                            "WB_WLD_OIL_RENTS_PCT_GDP",
                            "WB_WLD_NATURAL_GAS_RENTS_PCT_GDP",
                            "WB_WLD_COAL_RENTS_PCT_GDP",
                            "WB_WLD_ORES_RENTS_PCT_GDP",
                        ]
                    ),
                ),
            ],
        },
        {
            "dimension": "金融市场/资产价格",
            "items": [
                ("美股标普500", in_core(["US_SPX_LEVEL"]) + in_panel(["US_SPX_LEVEL"])),
                ("日经225", in_core(["JP_NIKKEI225_LEVEL"]) + in_panel(["JP_NIKKEI225_LEVEL"])),
                ("欧股Stoxx50", in_core(["EU_STOXX50E_LEVEL"]) + in_panel(["EU_STOXX50E_LEVEL"])),
                ("美元指数", in_core(["DXY_LEVEL"]) + in_panel(["DXY_LEVEL"])),
                ("美元兑英镑", in_core(["UK_BOE_USD_GBP_EXCHANGE_RATE"]) + in_panel(["UK_BOE_USD_GBP_EXCHANGE_RATE"])),
                ("黄金收益(FF)", in_core(["US_FF49_Gold_RET"]) + in_panel(["US_FF49_Gold_RET"])),
                ("油价(英国序列)", in_core(["UK_BOE_A1_38_Oil_prices"]) + in_panel(["UK_BOE_A1_38_Oil_prices"])),
                ("工业金属收益(FF)", in_core(["US_FF38IND_Metal_RET"]) + in_panel(["US_FF38IND_Metal_RET"])),
                ("美国长端利率", in_core(["US_IR_LONG_OECD_LEVEL"]) + in_panel(["US_IR_LONG_OECD_LEVEL"])),
                ("美国短端利率", in_core(["US_IR_SHORT_OECD_LEVEL"]) + in_panel(["US_IR_SHORT_OECD_LEVEL"])),
            ],
        },
        {
            "dimension": "住房/地产",
            "items": [
                (
                    "英国房价指数",
                    in_core(["UK_BOE_HOUSE_PRICE_INDEX_2015_01_100_EXT_OECD"])
                    + in_panel(["UK_BOE_HOUSE_PRICE_INDEX_2015_01_100_EXT_OECD"]),
                ),
            ],
        },
        {
            "dimension": "制度/治理",
            "items": [
                (
                    "政府效能(全球GDP加权)",
                    in_core(["DERIVED_GDPW_GOV_EFF"]) + in_panel(["DERIVED_GDPW_GOV_EFF"]),
                ),
                (
                    "法治(全球GDP加权)",
                    in_core(["DERIVED_GDPW_RULE_OF_LAW"]) + in_panel(["DERIVED_GDPW_RULE_OF_LAW"]),
                ),
                (
                    "腐败控制(全球GDP加权)",
                    in_core(["DERIVED_GDPW_CORRUPTION"]) + in_panel(["DERIVED_GDPW_CORRUPTION"]),
                ),
                *[
                    (
                        f"政府效能({name})",
                        in_core([f"WB_{code}_GOV_GOVERNMENT_EFFECTIVENESS"])
                        + in_panel([f"WB_{code}_GOV_GOVERNMENT_EFFECTIVENESS"]),
                    )
                    for code, name in CORE_COUNTRIES
                ],
                *[
                    (
                        f"法治({name})",
                        in_core([f"WB_{code}_GOV_RULE_OF_LAW"]) + in_panel([f"WB_{code}_GOV_RULE_OF_LAW"]),
                    )
                    for code, name in CORE_COUNTRIES
                ],
                *[
                    (
                        f"腐败控制({name})",
                        in_core([f"WB_{code}_GOV_CONTROL_OF_CORRUPTION"])
                        + in_panel([f"WB_{code}_GOV_CONTROL_OF_CORRUPTION"]),
                    )
                    for code, name in CORE_COUNTRIES
                ],
            ],
        },
        {
            "dimension": "超长历史锚",
            "items": [
                ("英国GDP/人均GDP(超长)", ["MPD_GBR_GDPPC_2011_INTL_EXT_WB_GROWTH"]),
                ("英国CPI(超长)", ["UK_CPI_INDEX_2015_100_EXT_WB"]),
                ("英国GDP综合指数(超长)", ["UK_GDP_COMPOSITE_INDEX_2013_100_EXT_WB"]),
                ("英国长端利率(Consols)", ["UK_BOE_CONSOLS_YIELD_PCT_EXT_OECD"]),
                ("英国股价指数", ["UK_BOE_SHARE_PRICES_INDEX_1962_04_100_EXT_OECD"]),
                ("英国银行利率", ["UK_BOE_BANK_RATE_PCT_EXT_OECD"]),
            ],
        },
    ]

    rows = []
    missing_rows = []
    for dim in dimensions:
        for label, candidates in dim["items"]:
            if not candidates:
                missing_rows.append({"dimension": dim["dimension"], "indicator": label, "reason": "no candidates in panel"})
                continue
            col = _pick_first_available(df, candidates)
            if not col:
                missing_rows.append({"dimension": dim["dimension"], "indicator": label, "reason": "no available column"})
                continue
            start_year, end_year, missing_pct = _series_span(df[col])
            rows.append(
                {
                    "dimension": dim["dimension"],
                    "indicator": label,
                    "column": col,
                    "category": _category_from_col(col),
                    "tier_used": "tier_modern" if col in core_set else "panel_only",
                    "frequency": "annual",
                    "huatai_category": _huatai_category_from_col(col, dim["dimension"]),
                    "start_year": start_year,
                    "end_year": end_year,
                    "missing_pct": round(missing_pct, 4),
                }
            )

    annual_out = pd.DataFrame(rows).drop_duplicates(subset=["column"]).reset_index(drop=True)

    monthly_df = pd.read_parquet(monthly_panel_path)
    if monthly_df.index.name is None:
        monthly_df.index = pd.to_datetime(monthly_df.index)

    monthly_rows = []
    monthly_excluded_rows = []
    for col in monthly_df.columns:
        huatai_cat = _huatai_category_from_col(col)
        if huatai_cat not in HUATAI_CATEGORIES:
            continue
        series = monthly_df[col]
        non_null_count = int(series.notna().sum())
        if non_null_count == 0:
            monthly_excluded_rows.append(
                {
                    "column": col,
                    "huatai_category": huatai_cat,
                    "reason": "all_missing",
                    "non_null_count": non_null_count,
                }
            )
            continue
        if non_null_count < MONTHLY_MIN_OBS:
            monthly_excluded_rows.append(
                {
                    "column": col,
                    "huatai_category": huatai_cat,
                    "reason": f"too_short(<{MONTHLY_MIN_OBS})",
                    "non_null_count": non_null_count,
                }
            )
            continue
        start_year, end_year, missing_pct = _series_span(series)
        monthly_rows.append(
            {
                "dimension": huatai_cat,
                "indicator": col,
                "column": col,
                "category": _category_from_col(col),
                "tier_used": "monthly_panel",
                "frequency": "monthly",
                "huatai_category": huatai_cat,
                "start_year": start_year,
                "end_year": end_year,
                "missing_pct": round(missing_pct, 4),
            }
        )

    monthly_out = pd.DataFrame(monthly_rows).drop_duplicates(subset=["column"]).reset_index(drop=True)
    out = pd.concat([annual_out, monthly_out], ignore_index=True)

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_csv, index=False)

    counts = out.groupby("dimension", as_index=False).size().sort_values("size", ascending=False)
    huatai_counts = (
        out[out["huatai_category"].isin(HUATAI_CATEGORIES)]
        .groupby(["frequency", "huatai_category"], as_index=False)
        .size()
        .sort_values(["frequency", "size"], ascending=[True, False])
    )
    huatai_missing = sorted(set(HUATAI_CATEGORIES) - set(monthly_out["huatai_category"].unique()))
    missing = pd.DataFrame(missing_rows)
    monthly_excluded = pd.DataFrame(monthly_excluded_rows)

    lines = [
        "# Core indicator set (econ + sociology framework)",
        "",
        f"- Source panel: `{panel_path}`",
        f"- Tier preference: `{core_path}` (tier_modern first, fallback to panel)",
        f"- Output (csv): `{out_csv}`",
        f"- Total indicators: {len(out)}",
        f"- Core countries (GDP-weighted): {', '.join([name for _, name in CORE_COUNTRIES])}",
        "",
        "## Huatai coverage (monthly)",
        "",
        huatai_counts.to_markdown(index=False),
        "",
        f"- Missing categories (monthly): {', '.join(huatai_missing) if huatai_missing else 'None'}",
        f"- Monthly quality filter: non-null observations >= {MONTHLY_MIN_OBS}",
        f"- Monthly excluded columns: {len(monthly_excluded_rows)}",
        "",
        "## Dimensions",
        "",
        counts.to_markdown(index=False),
        "",
        "## Core set",
        "",
        out.to_markdown(index=False),
        "",
        "## Missing targets",
        "",
        missing.to_markdown(index=False) if not missing.empty else "None",
        "",
        "## Monthly Excluded Columns (quality gate)",
        "",
        monthly_excluded.to_markdown(index=False) if not monthly_excluded.empty else "None",
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
