from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List


@dataclass(frozen=True)
class IndicatorSpec:
    id: str
    name: str
    category: str
    primary_source: str  # 'tushare', 'akshare', 'openbb'
    backend: str  # e.g. 'cn_cpi', 'cn_m', 'index_daily', 'ff_us_portfolio_returns'
    params: Dict[str, Any]
    base_freq: str  # 'A', 'Q', 'M', 'D'
    value_type: str  # 'level', 'index', 'rate_level', 'rate_yoy', 'rate_mom', 'price', 'price_adj', 'return'


def _slug(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s)
    return s.strip("_") or "NA"


def _ts_macro(id_: str, name: str, category: str, backend: str, field: str, value_type: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="tushare",
        backend=backend,
        params={"field": field},
        base_freq="M",
        value_type=value_type,
    )


def _ts_gdp(id_: str, name: str, category: str, field: str, value_type: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="tushare",
        backend="cn_gdp",
        params={"field": field},
        base_freq="Q",
        value_type=value_type,
    )


def _ts_rate(id_: str, name: str, category: str, backend: str, field: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="tushare",
        backend=backend,
        params={"field": field},
        base_freq="D",
        value_type="rate_level",
    )


def _ts_index_price(id_: str, name: str, ts_code: str, start_date: str = "19900101") -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category="CN/Equity",
        primary_source="tushare",
        backend="index_daily",
        params={"ts_code": ts_code, "start_date": start_date, "field": "close"},
        base_freq="D",
        value_type="price",
    )


def _ts_index_dailybasic(id_: str, name: str, ts_code: str, field: str, value_type: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category="CN/EquityValuation",
        primary_source="tushare",
        backend="index_dailybasic",
        params={"ts_code": ts_code, "start_date": "20040101", "field": field},
        base_freq="D",
        value_type=value_type,
    )


def _ts_sw_daily(id_: str, name: str, category: str, ts_code: str, field: str, value_type: str, start_date: str = "20120101") -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="tushare",
        backend="sw_daily",
        params={"ts_code": ts_code, "start_date": start_date, "field": field},
        base_freq="D",
        value_type=value_type,
    )


def _ts_ci_daily(id_: str, name: str, category: str, ts_code: str, field: str, value_type: str, start_date: str = "19900101") -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="tushare",
        backend="ci_daily",
        params={"ts_code": ts_code, "start_date": start_date, "field": field},
        base_freq="D",
        value_type=value_type,
    )


def _ts_fund_daily_price(id_: str, name: str, category: str, ts_code: str, start_date: str = "19900101") -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="tushare",
        backend="fund_daily",
        params={"ts_code": ts_code, "start_date": start_date, "field": "close"},
        base_freq="D",
        value_type="price",
    )


def _openbb_price(id_: str, name: str, category: str, symbol: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="openbb",
        backend="index_price",
        params={"symbol": symbol, "price_field": "adj_close", "start_date": "1960-01-01", "end_date": "2025-12-31"},
        base_freq="D",
        value_type="price_adj",
    )


def _openbb_oecd(id_: str, name: str, category: str, endpoint: str, params: dict[str, Any], value_type: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="openbb",
        backend="oecd_series",
        params={"endpoint": endpoint, "params": params},
        base_freq="M",
        value_type=value_type,
    )


def _openbb_ff_portfolio(id_: str, name: str, category: str, portfolio: str, portfolio_name: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="openbb",
        backend="ff_us_portfolio_returns",
        params={
            "portfolio": portfolio,
            "portfolio_name": portfolio_name,
            "frequency": "monthly",
            "start_date": "1960-01-01",
            "end_date": "2024-12-31",
        },
        base_freq="M",
        value_type="return",
    )


def _openbb_ff_factor(id_: str, name: str, category: str, factor: str, field: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="openbb",
        backend="ff_factors",
        params={
            "region": "america",
            "factor": factor,
            "field": field,
            "frequency": "monthly",
            "start_date": "1960-01-01",
            "end_date": "2024-12-31",
        },
        base_freq="M",
        value_type="return",
    )


def _ak_macro(id_: str, name: str, category: str, func: str, field: str, value_type: str) -> IndicatorSpec:
    return IndicatorSpec(
        id=id_,
        name=name,
        category=category,
        primary_source="akshare",
        backend="ak_macro",
        params={"func": func, "field": field},
        base_freq="M",
        value_type=value_type,
    )


INDICATORS: List[IndicatorSpec] = []

# -------------------------
# China macro (Tushare Pro)
# -------------------------

# CPI (Tushare provides YoY/MoM directly; keep those rather than re-deriving)
INDICATORS += [
    _ts_macro("CN_CPI_NT_YOY", "中国CPI同比(全国)", "CN/Inflation", "cn_cpi", "nt_yoy", "rate_yoy"),
    _ts_macro("CN_CPI_NT_MOM", "中国CPI环比(全国)", "CN/Inflation", "cn_cpi", "nt_mom", "rate_mom"),
    _ts_macro("CN_CPI_TOWN_YOY", "中国CPI同比(城市)", "CN/Inflation", "cn_cpi", "town_yoy", "rate_yoy"),
    _ts_macro("CN_CPI_TOWN_MOM", "中国CPI环比(城市)", "CN/Inflation", "cn_cpi", "town_mom", "rate_mom"),
    _ts_macro("CN_CPI_CNT_YOY", "中国CPI同比(农村)", "CN/Inflation", "cn_cpi", "cnt_yoy", "rate_yoy"),
    _ts_macro("CN_CPI_CNT_MOM", "中国CPI环比(农村)", "CN/Inflation", "cn_cpi", "cnt_mom", "rate_mom"),
]

# PPI (YoY + MoM +累计)
_PPI_FIELDS = [
    # yoy
    "ppi_yoy",
    "ppi_mp_yoy",
    "ppi_mp_qm_yoy",
    "ppi_mp_rm_yoy",
    "ppi_mp_p_yoy",
    "ppi_cg_yoy",
    "ppi_cg_f_yoy",
    "ppi_cg_c_yoy",
    "ppi_cg_adu_yoy",
    "ppi_cg_dcg_yoy",
    # mom
    "ppi_mom",
    "ppi_mp_mom",
    "ppi_mp_qm_mom",
    "ppi_mp_rm_mom",
    "ppi_mp_p_mom",
    "ppi_cg_mom",
    "ppi_cg_f_mom",
    "ppi_cg_c_mom",
    "ppi_cg_adu_mom",
    "ppi_cg_dcg_mom",
    # accu
    "ppi_accu",
    "ppi_mp_accu",
    "ppi_mp_qm_accu",
    "ppi_mp_rm_accu",
    "ppi_mp_p_accu",
    "ppi_cg_accu",
    "ppi_cg_f_accu",
    "ppi_cg_c_accu",
    "ppi_cg_adu_accu",
    "ppi_cg_dcg_accu",
]
for field in _PPI_FIELDS:
    if field.endswith("_yoy"):
        vt = "rate_yoy"
        label = "同比"
    elif field.endswith("_mom"):
        vt = "rate_mom"
        label = "环比"
    else:
        vt = "rate_level"
        label = "累计"
    INDICATORS.append(_ts_macro(f"CN_PPI_{field.upper()}", f"中国PPI({label}) {field}", "CN/Inflation", "cn_ppi", field, vt))

# Money supply (M0/M1/M2)
_MONEY_FIELDS = [
    ("m0", "中国M0(量)", "level"),
    ("m0_yoy", "中国M0同比", "rate_yoy"),
    ("m0_mom", "中国M0环比", "rate_mom"),
    ("m1", "中国M1(量)", "level"),
    ("m1_yoy", "中国M1同比", "rate_yoy"),
    ("m1_mom", "中国M1环比", "rate_mom"),
    ("m2", "中国M2(量)", "level"),
    ("m2_yoy", "中国M2同比", "rate_yoy"),
    ("m2_mom", "中国M2环比", "rate_mom"),
]
for field, name, vt in _MONEY_FIELDS:
    INDICATORS.append(_ts_macro(f"CN_M_{field.upper()}", name, "CN/MoneyCredit", "cn_m", field, vt))

# GDP (Quarterly, long history; Tushare cn_gdp)
INDICATORS += [
    _ts_gdp("CN_GDP_GDP", "中国GDP(季度累计)", "CN/Growth", "gdp", "level"),
    _ts_gdp("CN_GDP_GDP_YOY", "中国GDP同比(季度累计)", "CN/Growth", "gdp_yoy", "rate_yoy"),
    _ts_gdp("CN_GDP_PI", "第一产业增加值(季度累计)", "CN/Growth", "pi", "level"),
    _ts_gdp("CN_GDP_PI_YOY", "第一产业增加值同比(季度累计)", "CN/Growth", "pi_yoy", "rate_yoy"),
    _ts_gdp("CN_GDP_SI", "第二产业增加值(季度累计)", "CN/Growth", "si", "level"),
    _ts_gdp("CN_GDP_SI_YOY", "第二产业增加值同比(季度累计)", "CN/Growth", "si_yoy", "rate_yoy"),
    _ts_gdp("CN_GDP_TI", "第三产业增加值(季度累计)", "CN/Growth", "ti", "level"),
    _ts_gdp("CN_GDP_TI_YOY", "第三产业增加值同比(季度累计)", "CN/Growth", "ti_yoy", "rate_yoy"),
]

# PMI codes (headline + sub-indices; keep as a level-like series, diffs are more meaningful than pct_change)
_PMI_FIELDS = [
    "PMI010000",
    "PMI010100",
    "PMI010200",
    "PMI010300",
    "PMI010400",
    "PMI010401",
    "PMI010402",
    "PMI010403",
    "PMI010500",
    "PMI010501",
    "PMI010502",
    "PMI010503",
    "PMI010600",
    "PMI010601",
    "PMI010602",
    "PMI010603",
    "PMI010700",
    "PMI010701",
    "PMI010702",
    "PMI010703",
    "PMI010800",
    "PMI010801",
    "PMI010802",
    "PMI010803",
    "PMI010900",
    "PMI011000",
    "PMI011100",
    "PMI011200",
    "PMI011300",
    "PMI011400",
    "PMI011500",
    "PMI011600",
    "PMI011700",
    "PMI011800",
    "PMI011900",
    "PMI012000",
    # non-manufacturing / composite
    "PMI020100",
    "PMI020101",
    "PMI020102",
    "PMI020200",
    "PMI020201",
    "PMI020202",
    "PMI020300",
    "PMI020301",
    "PMI020302",
    "PMI020400",
    "PMI020401",
    "PMI020402",
    "PMI020500",
    "PMI020501",
    "PMI020502",
    "PMI020600",
    "PMI020601",
    "PMI020602",
    "PMI020700",
    "PMI020800",
    "PMI020900",
    "PMI021000",
    "PMI030000",
]

_PMI_FIELD_DESC: Dict[str, str] = {
    "PMI010000": "制造业PMI",
    "PMI010100": "制造业PMI:企业规模/大型企业",
    "PMI010200": "制造业PMI:企业规模/中型企业",
    "PMI010300": "制造业PMI:企业规模/小型企业",
    "PMI010400": "制造业PMI:构成指数/生产指数",
    "PMI010401": "制造业PMI:构成指数/生产指数:企业规模/大型企业",
    "PMI010402": "制造业PMI:构成指数/生产指数:企业规模/中型企业",
    "PMI010403": "制造业PMI:构成指数/生产指数:企业规模/小型企业",
    "PMI010500": "制造业PMI:构成指数/新订单指数",
    "PMI010501": "制造业PMI:构成指数/新订单指数:企业规模/大型企业",
    "PMI010502": "制造业PMI:构成指数/新订单指数:企业规模/中型企业",
    "PMI010503": "制造业PMI:构成指数/新订单指数:企业规模/小型企业",
    "PMI010600": "制造业PMI:构成指数/供应商配送时间指数",
    "PMI010601": "制造业PMI:构成指数/供应商配送时间指数:企业规模/大型企业",
    "PMI010602": "制造业PMI:构成指数/供应商配送时间指数:企业规模/中型企业",
    "PMI010603": "制造业PMI:构成指数/供应商配送时间指数:企业规模/小型企业",
    "PMI010700": "制造业PMI:构成指数/原材料库存指数",
    "PMI010701": "制造业PMI:构成指数/原材料库存指数:企业规模/大型企业",
    "PMI010702": "制造业PMI:构成指数/原材料库存指数:企业规模/中型企业",
    "PMI010703": "制造业PMI:构成指数/原材料库存指数:企业规模/小型企业",
    "PMI010800": "制造业PMI:构成指数/从业人员指数",
    "PMI010801": "制造业PMI:构成指数/从业人员指数:企业规模/大型企业",
    "PMI010802": "制造业PMI:构成指数/从业人员指数:企业规模/中型企业",
    "PMI010803": "制造业PMI:构成指数/从业人员指数:企业规模/小型企业",
    "PMI010900": "制造业PMI:其他/新出口订单",
    "PMI011000": "制造业PMI:其他/进口",
    "PMI011100": "制造业PMI:其他/采购量",
    "PMI011200": "制造业PMI:其他/主要原材料购进价格",
    "PMI011300": "制造业PMI:其他/出厂价格",
    "PMI011400": "制造业PMI:其他/产成品库存",
    "PMI011500": "制造业PMI:其他/在手订单",
    "PMI011600": "制造业PMI:其他/生产经营活动预期",
    "PMI011700": "制造业PMI:分行业/装备制造业",
    "PMI011800": "制造业PMI:分行业/高技术制造业",
    "PMI011900": "制造业PMI:分行业/基础原材料制造业",
    "PMI012000": "制造业PMI:分行业/消费品制造业",
    "PMI020100": "非制造业PMI:商务活动",
    "PMI020101": "非制造业PMI:商务活动:分行业/建筑业",
    "PMI020102": "非制造业PMI:商务活动:分行业/服务业业",
    "PMI020200": "非制造业PMI:新订单指数",
    "PMI020201": "非制造业PMI:新订单指数:分行业/建筑业",
    "PMI020202": "非制造业PMI:新订单指数:分行业/服务业",
    "PMI020300": "非制造业PMI:投入品价格指数",
    "PMI020301": "非制造业PMI:投入品价格指数:分行业/建筑业",
    "PMI020302": "非制造业PMI:投入品价格指数:分行业/服务业",
    "PMI020400": "非制造业PMI:销售价格指数",
    "PMI020401": "非制造业PMI:销售价格指数:分行业/建筑业",
    "PMI020402": "非制造业PMI:销售价格指数:分行业/服务业",
    "PMI020500": "非制造业PMI:从业人员指数",
    "PMI020501": "非制造业PMI:从业人员指数:分行业/建筑业",
    "PMI020502": "非制造业PMI:从业人员指数:分行业/服务业",
    "PMI020600": "非制造业PMI:业务活动预期指数",
    "PMI020601": "非制造业PMI:业务活动预期指数:分行业/建筑业",
    "PMI020602": "非制造业PMI:业务活动预期指数:分行业/服务业",
    "PMI020700": "非制造业PMI:新出口订单",
    "PMI020800": "非制造业PMI:在手订单",
    "PMI020900": "非制造业PMI:存货",
    "PMI021000": "非制造业PMI:供应商配送时间",
    "PMI030000": "中国综合PMI:产出指数",
}
for code in _PMI_FIELDS:
    desc = _PMI_FIELD_DESC.get(code, code)
    INDICATORS.append(_ts_macro(f"CN_PMI_{code}", f"中国PMI: {desc}", "CN/PMI", "cn_pmi", code, "rate_level"))

# Interbank rates
for tenor in ["on", "1w", "2w", "1m", "3m", "6m", "9m", "1y"]:
    INDICATORS.append(_ts_rate(f"CN_SHIBOR_{tenor.upper()}", f"Shibor {tenor}", "CN/Rates", "shibor", tenor))
for tenor in ["on", "1w", "2w", "1m", "2m", "3m", "6m", "12m"]:
    INDICATORS.append(_ts_rate(f"HK_HIBOR_{tenor.upper()}", f"Hibor {tenor}", "HK/Rates", "hibor", tenor))

# Equity indices (prices)
INDICATORS += [
    _ts_index_price("IDX_SH_COMP", "上证综指(价格)", "000001.SH"),
    _ts_index_price("IDX_SZ_COMP", "深证成指(价格)", "399001.SZ", start_date="19910101"),
    _ts_index_price("IDX_HS300", "沪深300(价格)", "000300.SH", start_date="20050101"),
    _ts_index_price("IDX_CSI500", "中证500(价格)", "000905.SH", start_date="20050101"),
    _ts_index_price("IDX_CSI1000", "中证1000(价格)", "000852.SH", start_date="20050101"),
    _ts_index_price("IDX_SSE50", "上证50(价格)", "000016.SH", start_date="20040101"),
    _ts_index_price("IDX_GEM", "创业板指(价格)", "399006.SZ", start_date="20100601"),
    _ts_index_price("IDX_STAR50", "科创50(价格)", "000688.SH", start_date="20200723"),
]

# Smart-beta / style indices (CSI; factor-like proxies)
INDICATORS += [
    _ts_index_price("IDX_CSI300R_GROWTH", "沪深300R成长(价格)", "000920.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI300R_VALUE", "沪深300R价值(价格)", "000921.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI300_DIVIDEND", "沪深300红利(价格)", "000821.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI500_GROWTH", "中证500成长(价格)", "h30351.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI500_VALUE", "中证500价值(价格)", "h30352.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI800_GROWTH", "中证800成长(价格)", "h30355.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI800_VALUE", "中证800价值(价格)", "h30356.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI300_VOL", "沪深300波动(价格)", "000803.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI300_HIGH_BETA", "沪深300高贝塔(价格)", "000828.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI300_LOW_BETA", "沪深300低贝塔(价格)", "000829.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI500_DIVIDEND", "中证500红利(价格)", "000822.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI_DIVIDEND", "中证红利(价格)", "000922.CSI", start_date="20050101"),
    _ts_index_price("IDX_CSI_DIVIDEND_TR", "中证红利全收益(价格)", "h00922.CSI", start_date="20050101"),
    _ts_index_price("IDX_SSE_DIVIDEND", "上证红利(价格)", "000015.SH", start_date="20050104"),
    _ts_index_price("IDX_SSE_DIVIDEND_TR", "上证红利收益(价格)", "h00015.SH", start_date="20050104"),
    _ts_index_price("IDX_CSI500_VOL", "中证500波动(价格)", "000804.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI500_HIGH_BETA", "中证500高贝塔(价格)", "000830.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI500_LOW_BETA", "中证500低贝塔(价格)", "000831.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI300_MOM", "沪深300动量(价格)", "h30260.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI_DIV_LOWVOL", "红利低波(价格)", "h30269.CSI", start_date="20090101"),
    _ts_index_price("IDX_CSI_DIV_VALUE", "红利价值(价格)", "h30270.CSI", start_date="20090101"),
    _ts_index_price("IDX_SSE_DIV_LOWVOL", "上证红利低波(价格)", "h50040.CSI", start_date="20090101"),
]

# China industry indices: use CITIC as the default (via ci_daily).
_CITIC_L1 = [
    ("CI005001.CI", "石油石化"),
    ("CI005002.CI", "煤炭"),
    ("CI005003.CI", "有色金属"),
    ("CI005004.CI", "电力及公用事业"),
    ("CI005005.CI", "钢铁"),
    ("CI005006.CI", "基础化工"),
    ("CI005007.CI", "建筑"),
    ("CI005008.CI", "建材"),
    ("CI005009.CI", "轻工制造"),
    ("CI005010.CI", "机械"),
    ("CI005011.CI", "电力设备及新能源"),
    ("CI005012.CI", "国防军工"),
    ("CI005013.CI", "汽车"),
    ("CI005014.CI", "商贸零售"),
    ("CI005015.CI", "消费者服务"),
    ("CI005016.CI", "家电"),
    ("CI005017.CI", "纺织服装"),
    ("CI005018.CI", "医药"),
    ("CI005019.CI", "食品饮料"),
    ("CI005020.CI", "农林牧渔"),
    ("CI005021.CI", "银行"),
    ("CI005022.CI", "非银行金融"),
    ("CI005023.CI", "房地产"),
    ("CI005024.CI", "交通运输"),
    ("CI005025.CI", "电子"),
    ("CI005026.CI", "通信"),
    ("CI005027.CI", "计算机"),
    ("CI005028.CI", "传媒"),
    ("CI005029.CI", "综合"),
    ("CI005030.CI", "综合金融"),
]
for code, name in _CITIC_L1:
    id_code = code.replace(".", "_")
    INDICATORS.append(
        _ts_ci_daily(
            f"IDX_CITIC_L1_{id_code}",
            f"中信一级行业指数({name})",
            "CN/EquityIndustry(CITIC)",
            code,
            "close",
            "price",
        )
    )

# China factor ETFs (investable proxies; Tushare fund_daily)
INDICATORS += [
    _ts_fund_daily_price("ETF_HS300_510300", "沪深300ETF(510300)", "CN/EquityETF", "510300.SH", start_date="20120101"),
    _ts_fund_daily_price("ETF_HS300_159919", "沪深300ETF(159919)", "CN/EquityETF", "159919.SZ", start_date="20120101"),
    _ts_fund_daily_price("ETF_SSE_DIVIDEND_510880", "红利ETF(510880)", "CN/EquityFactorETF", "510880.SH", start_date="20070118"),
    _ts_fund_daily_price("ETF_SZ_DIVIDEND_159905", "深红利ETF(159905)", "CN/EquityFactorETF", "159905.SZ", start_date="20110111"),
    _ts_fund_daily_price("ETF_DIV_LOWVOL_512890", "红利低波ETF(512890)", "CN/EquityFactorETF", "512890.SH", start_date="20190118"),
    _ts_fund_daily_price("ETF_HS300_DIV_LOWVOL_515300", "300红利低波ETF(515300)", "CN/EquityFactorETF", "515300.SH", start_date="20190919"),
    _ts_fund_daily_price("ETF_CSI_DIVIDEND_515180", "红利ETF(515180)", "CN/EquityFactorETF", "515180.SH", start_date="20191220"),
    _ts_fund_daily_price("ETF_CSI_DIVIDEND_515080", "中证红利ETF(515080)", "CN/EquityFactorETF", "515080.SH", start_date="20191227"),
    _ts_fund_daily_price("ETF_SSE_ESG_510090", "ESG建信ETF(510090)", "CN/EquityFactorETF", "510090.SH", start_date="20100809"),
]

# Equity valuation (index daily basic)
_IDX_DAILYBASIC_LEVEL = ["total_mv", "float_mv", "total_share", "float_share", "free_share"]
_IDX_DAILYBASIC_RATE = ["turnover_rate", "turnover_rate_f", "pe", "pe_ttm", "pb"]
_IDX_DAILYBASIC_INDEXES = [
    ("IDX_HS300", "沪深300", "000300.SH"),
    ("IDX_CSI500", "中证500", "000905.SH"),
    ("IDX_SSE50", "上证50", "000016.SH"),
    ("IDX_GEM", "创业板指", "399006.SZ"),
    ("IDX_SH_COMP", "上证综指", "000001.SH"),
    ("IDX_SZ_COMP", "深证成指", "399001.SZ"),
]
for prefix, label, ts_code in _IDX_DAILYBASIC_INDEXES:
    for f in _IDX_DAILYBASIC_LEVEL:
        INDICATORS.append(_ts_index_dailybasic(f"{prefix}_{f.upper()}", f"{label} {f}", ts_code, f, "level"))
    for f in _IDX_DAILYBASIC_RATE:
        INDICATORS.append(_ts_index_dailybasic(f"{prefix}_{f.upper()}", f"{label} {f}", ts_code, f, "rate_level"))

# -------------------------
# China macro (AkShare)
# -------------------------

INDICATORS += [
    _ak_macro("CN_EXPORT_YOY_AK", "中国出口同比(AkShare)", "CN/Macro(AkShare)", "macro_china_exports_yoy", "今值", "rate_yoy"),
    _ak_macro("CN_IMPORT_YOY_AK", "中国进口同比(AkShare)", "CN/Macro(AkShare)", "macro_china_imports_yoy", "今值", "rate_yoy"),
    _ak_macro("CN_TRADE_BALANCE_AK", "中国贸易差额(AkShare)", "CN/Macro(AkShare)", "macro_china_trade_balance", "今值", "level"),
    _ak_macro("CN_IP_YOY_AK", "中国工业增加值同比(AkShare)", "CN/Macro(AkShare)", "macro_china_industrial_production_yoy", "今值", "rate_yoy"),
    _ak_macro("CN_RETAIL_YOY_AK", "中国社零同比(AkShare)", "CN/Macro(AkShare)", "macro_china_consumer_goods_retail", "同比增长", "rate_yoy"),
    _ak_macro("CN_FAI_YOY_AK", "中国固定资产投资同比(AkShare)", "CN/Macro(AkShare)", "macro_china_gdzctz", "同比增长", "rate_yoy"),
    _ak_macro("CN_GYZJZ_YOY_AK", "中国工业企业增加值同比(AkShare)", "CN/Macro(AkShare)", "macro_china_gyzjz", "同比增长", "rate_yoy"),
    _ak_macro("CN_ELECTRICITY_TOTAL_AK", "全社会用电量(AkShare)", "CN/Macro(AkShare)", "macro_china_society_electricity", "全社会用电量", "level"),
    _ak_macro("CN_NEW_HOUSE_PRICE_YOY_AK", "新建商品住宅价格指数同比(AkShare)", "CN/RealEstate(AkShare)", "macro_china_new_house_price", "新建商品住宅价格指数-同比", "rate_yoy"),
    _ak_macro("CN_REAL_ESTATE_VALUE_AK", "房地产景气指数(AkShare)", "CN/RealEstate(AkShare)", "macro_china_real_estate", "最新值", "level"),
    _ak_macro("CN_COMMODITY_PRICE_INDEX_AK", "中国大宗商品价格指数(AkShare)", "CN/Commodity(AkShare)", "macro_china_commodity_price_index", "最新值", "index"),
    _ak_macro("CN_RRR_LARGE_PRE_AK", "存款准备金率(大型机构-调整前)(AkShare)", "CN/Rates(AkShare)", "macro_china_reserve_requirement_ratio", "大型金融机构-调整前", "rate_level"),
    _ak_macro("CN_SHIBOR_ON_AK", "Shibor O/N(定价)(AkShare)", "CN/Rates(AkShare)", "macro_china_shibor_all", "O/N-定价", "rate_level"),
    _ak_macro("CN_MARGIN_SH_FIN_AK", "上交所融资余额(AkShare)", "CN/EquityFlow(AkShare)", "macro_china_market_margin_sh", "融资余额", "level"),
    _ak_macro("CN_MARGIN_SZ_FIN_AK", "深交所融资余额(AkShare)", "CN/EquityFlow(AkShare)", "macro_china_market_margin_sz", "融资余额", "level"),
    _ak_macro("CN_STOCK_SHARES_SH_AK", "A股发行总股本-上海(AkShare)", "CN/Equity(AkShare)", "macro_china_stock_market_cap", "发行总股本-上海", "level"),
    _ak_macro("CN_CPI_LEVEL_AK", "中国CPI当月(AkShare)", "CN/Inflation(AkShare)", "macro_china_cpi", "全国-当月", "index"),
    _ak_macro("CN_PPI_LEVEL_AK", "中国PPI当月(AkShare)", "CN/Inflation(AkShare)", "macro_china_ppi", "当月", "index"),
    _ak_macro("CN_M2_LEVEL_AK", "中国M2余额(AkShare)", "CN/MoneyCredit(AkShare)", "macro_china_money_supply", "货币和准货币(M2)-数量(亿元)", "level"),
    _ak_macro("CN_SOCIAL_FIN_AK", "中国社融增量(AkShare)", "CN/Macro(AkShare)", "macro_china_shrzgm", "当月", "level"),
    _ak_macro("CN_NEW_CREDIT_AK", "中国新增信贷(AkShare)", "CN/Macro(AkShare)", "macro_china_new_financial_credit", "当月", "level"),
    _ak_macro("CN_LPR_1Y_AK", "中国LPR 1Y(AkShare)", "CN/Rates(AkShare)", "macro_china_lpr", "LPR1Y", "rate_level"),
    _ak_macro("CN_LPR_5Y_AK", "中国LPR 5Y(AkShare)", "CN/Rates(AkShare)", "macro_china_lpr", "LPR5Y", "rate_level"),
]

# -------------------------
# Global market (OpenBB / yfinance)
# -------------------------

INDICATORS += [
    _openbb_price("US_SPX", "标普500(调整价)", "Global/Equity", "^GSPC"),
    _openbb_price("US_NDX", "纳指100(调整价)", "Global/Equity", "^NDX"),
    _openbb_price("US_DJI", "道琼斯(调整价)", "Global/Equity", "^DJI"),
    _openbb_price("JP_NIKKEI225", "日经225(调整价)", "Global/Equity", "^N225"),
    _openbb_price("EU_STOXX50E", "欧股Stoxx50(调整价)", "Global/Equity", "^STOXX50E"),
    _openbb_price("DXY", "美元指数DXY(调整价)", "Global/FX", "DX-Y.NYB"),
    _openbb_price("USDCNY", "美元兑人民币(调整价)", "Global/FX", "USDCNY=X"),
    _openbb_price("GOLD", "黄金期货(调整价)", "Global/Commodity", "GC=F"),
    _openbb_price("SILVER", "白银期货(调整价)", "Global/Commodity", "SI=F"),
    _openbb_price("WTI", "WTI原油期货(调整价)", "Global/Commodity", "CL=F"),
    _openbb_price("COPPER", "铜期货(调整价)", "Global/Commodity", "HG=F"),
]

# Global factor ETFs (investable factor proxies)
INDICATORS += [
    _openbb_price("US_ETF_MTUM", "美股动量ETF MTUM(调整价)", "Global/EquityFactorETF", "MTUM"),
    _openbb_price("US_ETF_QUAL", "美股质量ETF QUAL(调整价)", "Global/EquityFactorETF", "QUAL"),
    _openbb_price("US_ETF_USMV", "美股低波ETF USMV(调整价)", "Global/EquityFactorETF", "USMV"),
    _openbb_price("US_ETF_VLUE", "美股价值ETF VLUE(调整价)", "Global/EquityFactorETF", "VLUE"),
    _openbb_price("US_ETF_VUG", "美股成长ETF VUG(调整价)", "Global/EquityFactorETF", "VUG"),
    _openbb_price("US_ETF_VIG", "美股股息ETF VIG(调整价)", "Global/EquityFactorETF", "VIG"),
]

# OECD macro (OpenBB, long history, no key required)
INDICATORS += [
    _openbb_oecd(
        "US_CPI_YOY_OECD",
        "美国CPI同比(OECD)",
        "US/Macro(OECD)",
        "cpi",
        {"country": "united_states", "transform": "yoy", "frequency": "monthly", "expenditure": "total"},
        "rate_yoy",
    ),
    _openbb_oecd(
        "US_UNRATE_OECD",
        "美国失业率(OECD)",
        "US/Macro(OECD)",
        "unemployment",
        {"country": "united_states", "frequency": "monthly"},
        "rate_level",
    ),
    _openbb_oecd(
        "US_IR_SHORT_OECD",
        "美国短端利率(OECD)",
        "US/Rates(OECD)",
        "interest_rates",
        {"country": "united_states", "duration": "short", "frequency": "monthly"},
        "rate_level",
    ),
    _openbb_oecd(
        "US_IR_LONG_OECD",
        "美国长端利率(OECD)",
        "US/Rates(OECD)",
        "interest_rates",
        {"country": "united_states", "duration": "long", "frequency": "monthly"},
        "rate_level",
    ),
]

# -------------------------
# US fine-grained assets (Fama-French)
# -------------------------

def _add_ff_portfolio_set(
    id_prefix: str,
    name_prefix: str,
    category: str,
    portfolio: str,
    portfolio_names: list[str],
) -> None:
    for pname in portfolio_names:
        INDICATORS.append(_openbb_ff_portfolio(f"{id_prefix}{_slug(pname)}", f"{name_prefix}: {pname}", category, portfolio, pname))


# FF 49 Industry Portfolios
_FF49_NAMES = [
    "Aero",
    "Agric",
    "Autos",
    "Banks",
    "Beer",
    "BldMt",
    "Books",
    "Boxes",
    "BusSv",
    "Chems",
    "Chips",
    "Clths",
    "Cnstr",
    "Coal",
    "Drugs",
    "ElcEq",
    "FabPr",
    "Fin",
    "Food",
    "Fun",
    "Gold",
    "Guns",
    "Hardw",
    "Hlth",
    "Hshld",
    "Insur",
    "LabEq",
    "Mach",
    "Meals",
    "MedEq",
    "Mines",
    "Oil",
    "Other",
    "Paper",
    "PerSv",
    "RlEst",
    "Rtail",
    "Rubbr",
    "Ships",
    "Smoke",
    "Soda",
    "Softw",
    "Steel",
    "Telcm",
    "Toys",
    "Trans",
    "Txtls",
    "Util",
    "Whlsl",
]
_add_ff_portfolio_set("US_FF49_", "FF 49行业收益", "US/FF/Industry49", "49_industry_portfolios", _FF49_NAMES)

# FF 25 Size x Value Portfolios (5x5)
_FF25_NAMES = [
    "SMALL LoBM",
    "ME1 BM2",
    "ME1 BM3",
    "ME1 BM4",
    "SMALL HiBM",
    "ME2 BM1",
    "ME2 BM2",
    "ME2 BM3",
    "ME2 BM4",
    "ME2 BM5",
    "ME3 BM1",
    "ME3 BM2",
    "ME3 BM3",
    "ME3 BM4",
    "ME3 BM5",
    "ME4 BM1",
    "ME4 BM2",
    "ME4 BM3",
    "ME4 BM4",
    "ME4 BM5",
    "BIG LoBM",
    "ME5 BM2",
    "ME5 BM3",
    "ME5 BM4",
    "BIG HiBM",
]
_add_ff_portfolio_set("US_FF25_", "FF 25组合收益(Size×Value)", "US/FF/SizeValue25", "25_portfolios_5x5", _FF25_NAMES)

# Industry portfolios (5 / 10 / 12 / 17 / 30 / 38 / 48)
_FF5IND_NAMES = ["Cnsmr", "HiTec", "Hlth", "Manuf", "Other"]
_add_ff_portfolio_set("US_FF5IND_", "FF 5行业收益", "US/FF/Industry5", "5_industry_portfolios", _FF5IND_NAMES)

_FF10IND_NAMES = ["Durbl", "Enrgy", "HiTec", "Hlth", "Manuf", "NoDur", "Other", "Shops", "Telcm", "Utils"]
_add_ff_portfolio_set("US_FF10IND_", "FF 10行业收益", "US/FF/Industry10", "10_industry_portfolios", _FF10IND_NAMES)

_FF12IND_NAMES = ["BusEq", "Chems", "Durbl", "Enrgy", "Hlth", "Manuf", "Money", "NoDur", "Other", "Shops", "Telcm", "Utils"]
_add_ff_portfolio_set("US_FF12IND_", "FF 12行业收益", "US/FF/Industry12", "12_industry_portfolios", _FF12IND_NAMES)

_FF17IND_NAMES = [
    "Cars",
    "Chems",
    "Clths",
    "Cnstr",
    "Cnsum",
    "Durbl",
    "FabPr",
    "Finan",
    "Food",
    "Machn",
    "Mines",
    "Oil",
    "Other",
    "Rtail",
    "Steel",
    "Trans",
    "Utils",
]
_add_ff_portfolio_set("US_FF17IND_", "FF 17行业收益", "US/FF/Industry17", "17_industry_portfolios", _FF17IND_NAMES)

_FF30IND_NAMES = [
    "Autos",
    "Beer",
    "Books",
    "BusEq",
    "Carry",
    "Chems",
    "Clths",
    "Cnstr",
    "Coal",
    "ElcEq",
    "FabPr",
    "Fin",
    "Food",
    "Games",
    "Hlth",
    "Hshld",
    "Meals",
    "Mines",
    "Oil",
    "Other",
    "Paper",
    "Rtail",
    "Servs",
    "Smoke",
    "Steel",
    "Telcm",
    "Trans",
    "Txtls",
    "Util",
    "Whlsl",
]
_add_ff_portfolio_set("US_FF30IND_", "FF 30行业收益", "US/FF/Industry30", "30_industry_portfolios", _FF30IND_NAMES)

_FF38IND_NAMES = [
    "Agric",
    "Apprl",
    "Cars",
    "Chair",
    "Chems",
    "Cnstr",
    "Elctr",
    "Food",
    "Garbg",
    "Glass",
    "Govt",
    "Instr",
    "Lethr",
    "Machn",
    "Manuf",
    "Metal",
    "Mines",
    "Money",
    "MtlPr",
    "Oil",
    "Other",
    "Paper",
    "Phone",
    "Print",
    "Ptrlm",
    "Rtail",
    "Rubbr",
    "Smoke",
    "Srvc",
    "Steam",
    "Stone",
    "TV",
    "Trans",
    "Txtls",
    "Utils",
    "Water",
    "Whlsl",
    "Wood",
]
_add_ff_portfolio_set("US_FF38IND_", "FF 38行业收益", "US/FF/Industry38", "38_industry_portfolios", _FF38IND_NAMES)

_FF48IND_NAMES = [
    "Aero",
    "Agric",
    "Autos",
    "Banks",
    "Beer",
    "BldMt",
    "Books",
    "Boxes",
    "BusSv",
    "Chems",
    "Chips",
    "Clths",
    "Cnstr",
    "Coal",
    "Comps",
    "Drugs",
    "ElcEq",
    "FabPr",
    "Fin",
    "Food",
    "Fun",
    "Gold",
    "Guns",
    "Hlth",
    "Hshld",
    "Insur",
    "LabEq",
    "Mach",
    "Meals",
    "MedEq",
    "Mines",
    "Oil",
    "Other",
    "Paper",
    "PerSv",
    "RlEst",
    "Rtail",
    "Rubbr",
    "Ships",
    "Smoke",
    "Soda",
    "Steel",
    "Telcm",
    "Toys",
    "Trans",
    "Txtls",
    "Util",
    "Whlsl",
]
_add_ff_portfolio_set("US_FF48IND_", "FF 48行业收益", "US/FF/Industry48", "48_industry_portfolios", _FF48IND_NAMES)

# 100 Size x Value Portfolios (10x10)
_FF100_NAMES = [
    "BIG HiBM",
    "BIG LoBM",
    "ME1 BM2",
    "ME1 BM3",
    "ME1 BM4",
    "ME1 BM5",
    "ME1 BM6",
    "ME1 BM7",
    "ME1 BM8",
    "ME1 BM9",
    "ME10 BM2",
    "ME10 BM3",
    "ME10 BM4",
    "ME10 BM5",
    "ME10 BM6",
    "ME10 BM7",
    "ME10 BM8",
    "ME10 BM9",
    "ME2 BM1",
    "ME2 BM10",
    "ME2 BM2",
    "ME2 BM3",
    "ME2 BM4",
    "ME2 BM5",
    "ME2 BM6",
    "ME2 BM7",
    "ME2 BM8",
    "ME2 BM9",
    "ME3 BM1",
    "ME3 BM10",
    "ME3 BM2",
    "ME3 BM3",
    "ME3 BM4",
    "ME3 BM5",
    "ME3 BM6",
    "ME3 BM7",
    "ME3 BM8",
    "ME3 BM9",
    "ME4 BM1",
    "ME4 BM10",
    "ME4 BM2",
    "ME4 BM3",
    "ME4 BM4",
    "ME4 BM5",
    "ME4 BM6",
    "ME4 BM7",
    "ME4 BM8",
    "ME4 BM9",
    "ME5 BM1",
    "ME5 BM10",
    "ME5 BM2",
    "ME5 BM3",
    "ME5 BM4",
    "ME5 BM5",
    "ME5 BM6",
    "ME5 BM7",
    "ME5 BM8",
    "ME5 BM9",
    "ME6 BM1",
    "ME6 BM10",
    "ME6 BM2",
    "ME6 BM3",
    "ME6 BM4",
    "ME6 BM5",
    "ME6 BM6",
    "ME6 BM7",
    "ME6 BM8",
    "ME6 BM9",
    "ME7 BM1",
    "ME7 BM10",
    "ME7 BM2",
    "ME7 BM3",
    "ME7 BM4",
    "ME7 BM5",
    "ME7 BM6",
    "ME7 BM7",
    "ME7 BM8",
    "ME7 BM9",
    "ME8 BM1",
    "ME8 BM10",
    "ME8 BM2",
    "ME8 BM3",
    "ME8 BM4",
    "ME8 BM5",
    "ME8 BM6",
    "ME8 BM7",
    "ME8 BM8",
    "ME8 BM9",
    "ME9 BM1",
    "ME9 BM10",
    "ME9 BM2",
    "ME9 BM3",
    "ME9 BM4",
    "ME9 BM5",
    "ME9 BM6",
    "ME9 BM7",
    "ME9 BM8",
    "ME9 BM9",
    "SMALL HiBM",
    "SMALL LoBM",
]
_add_ff_portfolio_set("US_FF100_", "FF 100组合收益(Size×Value 10x10)", "US/FF/SizeValue100", "100_portfolios_10x10", _FF100_NAMES)

# Additional 25-portfolio sorts (Investment / Profitability)
_FF25_ME_INV_NAMES = [
    "BIG HiINV",
    "BIG LoINV",
    "ME1 INV2",
    "ME1 INV3",
    "ME1 INV4",
    "ME2 INV1",
    "ME2 INV2",
    "ME2 INV3",
    "ME2 INV4",
    "ME2 INV5",
    "ME3 INV1",
    "ME3 INV2",
    "ME3 INV3",
    "ME3 INV4",
    "ME3 INV5",
    "ME4 INV1",
    "ME4 INV2",
    "ME4 INV3",
    "ME4 INV4",
    "ME4 INV5",
    "ME5 INV2",
    "ME5 INV3",
    "ME5 INV4",
    "SMALL HiINV",
    "SMALL LoINV",
]
_add_ff_portfolio_set("US_FF25_ME_INV_", "FF 25组合收益(Size×Inv)", "US/FF/SizeInv25", "25_portfolios_me_inv_5x5", _FF25_ME_INV_NAMES)

_FF25_ME_OP_NAMES = [
    "BIG HiOP",
    "BIG LoOP",
    "ME1 OP2",
    "ME1 OP3",
    "ME1 OP4",
    "ME2 OP1",
    "ME2 OP2",
    "ME2 OP3",
    "ME2 OP4",
    "ME2 OP5",
    "ME3 OP1",
    "ME3 OP2",
    "ME3 OP3",
    "ME3 OP4",
    "ME3 OP5",
    "ME4 OP1",
    "ME4 OP2",
    "ME4 OP3",
    "ME4 OP4",
    "ME4 OP5",
    "ME5 OP2",
    "ME5 OP3",
    "ME5 OP4",
    "SMALL HiOP",
    "SMALL LoOP",
]
_add_ff_portfolio_set("US_FF25_ME_OP_", "FF 25组合收益(Size×OP)", "US/FF/SizeOP25", "25_portfolios_me_op_5x5", _FF25_ME_OP_NAMES)

_FF25_BM_INV_NAMES = [
    "BM1 INV2",
    "BM1 INV3",
    "BM1 INV4",
    "BM2 INV1",
    "BM2 INV2",
    "BM2 INV3",
    "BM2 INV4",
    "BM2 INV5",
    "BM3 INV1",
    "BM3 INV2",
    "BM3 INV3",
    "BM3 INV4",
    "BM3 INV5",
    "BM4 INV1",
    "BM4 INV2",
    "BM4 INV3",
    "BM4 INV4",
    "BM4 INV5",
    "BM5 INV2",
    "BM5 INV3",
    "BM5 INV4",
    "HiBM HiINV",
    "HiBM LoINV",
    "LoBM HiINV",
    "LoBM LoINV",
]
_add_ff_portfolio_set("US_FF25_BM_INV_", "FF 25组合收益(BM×Inv)", "US/FF/ValueInv25", "25_portfolios_beme_inv_5x5", _FF25_BM_INV_NAMES)

_FF25_BM_OP_NAMES = [
    "BM1 OP2",
    "BM1 OP3",
    "BM1 OP4",
    "BM2 OP1",
    "BM2 OP2",
    "BM2 OP3",
    "BM2 OP4",
    "BM2 OP5",
    "BM3 OP1",
    "BM3 OP2",
    "BM3 OP3",
    "BM3 OP4",
    "BM3 OP5",
    "BM4 OP1",
    "BM4 OP2",
    "BM4 OP3",
    "BM4 OP4",
    "BM4 OP5",
    "BM5 OP2",
    "BM5 OP3",
    "BM5 OP4",
    "HiBM HiOP",
    "HiBM LoOP",
    "LoBM HiOP",
    "LoBM LoOP",
]
_add_ff_portfolio_set("US_FF25_BM_OP_", "FF 25组合收益(BM×OP)", "US/FF/ValueOP25", "25_portfolios_beme_op_5x5", _FF25_BM_OP_NAMES)

_FF25_OP_INV_NAMES = [
    "HiOP HiINV",
    "HiOP LoINV",
    "LoOP HiINV",
    "LoOP LoINV",
    "OP1 INV2",
    "OP1 INV3",
    "OP1 INV4",
    "OP2 INV1",
    "OP2 INV2",
    "OP2 INV3",
    "OP2 INV4",
    "OP2 INV5",
    "OP3 INV1",
    "OP3 INV2",
    "OP3 INV3",
    "OP3 INV4",
    "OP3 INV5",
    "OP4 INV1",
    "OP4 INV2",
    "OP4 INV3",
    "OP4 INV4",
    "OP4 INV5",
    "OP5 INV2",
    "OP5 INV3",
    "OP5 INV4",
]
_add_ff_portfolio_set("US_FF25_OP_INV_", "FF 25组合收益(OP×Inv)", "US/FF/OPInv25", "25_portfolios_op_inv_5x5", _FF25_OP_INV_NAMES)

# FF Factors
for field, label in [("mkt_rf", "MKT-RF"), ("smb", "SMB"), ("hml", "HML"), ("rf", "RF")]:
    INDICATORS.append(_openbb_ff_factor(f"US_FF3_{field.upper()}", f"FF3因子: {label}", "US/FF/Factors", "3_factors", field))
for field, label in [("rmw", "RMW"), ("cma", "CMA")]:
    INDICATORS.append(_openbb_ff_factor(f"US_FF5_{field.upper()}", f"FF5因子: {label}", "US/FF/Factors", "5_factors", field))
INDICATORS.append(_openbb_ff_factor("US_FF_MOM", "FF动量因子(MOM)", "US/FF/Factors", "momentum", "mom"))
INDICATORS.append(_openbb_ff_factor("US_FF_ST_REV", "FF短期反转(ST_REV)", "US/FF/Factors", "st_reversal", "st_rev"))
INDICATORS.append(_openbb_ff_factor("US_FF_LT_REV", "FF长期反转(LT_REV)", "US/FF/Factors", "lt_reversal", "lt_rev"))


INDICATOR_MAP: Dict[str, IndicatorSpec] = {ind.id: ind for ind in INDICATORS}
