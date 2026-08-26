#!/usr/bin/env python3
"""Assess whether UK long history can proxy a global C1 long wave."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, sosfiltfilt


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_annual_very_long_history_year.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c1_global_proxy_analysis.json"
COUNTRIES = (
    "GBR",
    "FRA",
    "NLD",
    "SWE",
    "ITA",
    "DEU",
    "USA",
    "CHN",
    "IND",
    "JPN",
    "ESP",
    "CAN",
    "AUS",
    "BRA",
    "KOR",
)
PERIOD_BAND = (35.0, 70.0)


def _finite(value: float | int | None, digits: int = 4) -> float | int | None:
    if value is None or not math.isfinite(float(value)):
        return None
    if isinstance(value, int):
        return value
    return round(float(value), digits)


def _robust_z(series: pd.Series) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    if not series.notna().any():
        return pd.Series(np.nan, index=series.index, dtype=float)
    median = series.median()
    scale = (series - median).abs().median() * 1.4826
    if not scale or pd.isna(scale):
        scale = series.std()
    if not scale or pd.isna(scale):
        return pd.Series(np.nan, index=series.index, dtype=float)
    return ((series - median) / scale).clip(-6.0, 6.0)


def _log_cagr(series: pd.Series, years: int = 10) -> pd.Series:
    levels = pd.to_numeric(series, errors="coerce").where(lambda values: values > 0)
    return (np.log(levels) - np.log(levels.shift(years))) / years


def _rolling_level(series: pd.Series, years: int = 10) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(years, min_periods=max(5, years - 3)).mean()


def _bandpass(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if len(valid) < 100:
        return pd.Series(dtype=float)
    years = pd.Index(range(int(valid.index.min()), int(valid.index.max()) + 1), name="year")
    filled = valid.reindex(years).interpolate(limit_direction="both")
    low_period, high_period = PERIOD_BAND
    sos = butter(
        3,
        (1.0 / high_period, 1.0 / low_period),
        btype="bandpass",
        fs=1.0,
        output="sos",
    )
    return pd.Series(sosfiltfilt(sos, filled.to_numpy(dtype=float)), index=years)


def _correlation(left: pd.Series, right: pd.Series) -> tuple[int, float | None]:
    frame = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if len(frame) < 8:
        return len(frame), None
    return len(frame), _finite(frame["left"].corr(frame["right"]))


def _best_lag(left: pd.Series, right: pd.Series, max_lag: int = 15) -> dict[str, Any]:
    candidates = []
    for lag in range(-max_lag, max_lag + 1):
        observations, correlation = _correlation(left, right.shift(lag))
        if correlation is not None:
            candidates.append((abs(correlation), lag, correlation, observations))
    if not candidates:
        return {"lagYears": None, "correlation": None, "observations": 0}
    _, lag, correlation, observations = max(candidates)
    return {
        "lagYears": lag,
        "correlation": correlation,
        "observations": observations,
        "warning": "低频序列仅用于相位差描述，不能据此认定因果领先关系。",
    }


def _era_correlations(left: pd.Series, right: pd.Series, eras: list[tuple[int, int]]) -> list[dict[str, Any]]:
    rows = []
    for start, end in eras:
        observations, correlation = _correlation(left.loc[start:end], right.loc[start:end])
        rows.append({"start": start, "end": end, "observations": observations, "correlation": correlation})
    return rows


def _proxy_result(raw: pd.Series, reference: pd.Series, *, start: int) -> dict[str, Any]:
    raw = raw.loc[start:]
    reference = reference.loc[start:]
    raw_wave = _bandpass(raw)
    reference_wave = _bandpass(reference)
    raw_observations, raw_correlation = _correlation(raw, reference)
    band_observations, band_correlation = _correlation(raw_wave, reference_wave)
    return {
        "start": int(max(raw.dropna().index.min(), reference.dropna().index.min())),
        "end": int(min(raw.dropna().index.max(), reference.dropna().index.max())),
        "rawCorrelation": raw_correlation,
        "rawObservations": raw_observations,
        "bandCorrelation": band_correlation,
        "bandObservations": band_observations,
        "effectiveLongWaves": _finite(band_observations / np.mean(PERIOD_BAND), 2),
        "bestAbsoluteLag": _best_lag(raw_wave, reference_wave),
    }


def _country_growth_panel(panel: pd.DataFrame) -> pd.DataFrame:
    growth = {}
    for country in COUNTRIES:
        column = f"MPD_{country}_GDPPC_2011_INTL_EXT_WB_GROWTH"
        if column in panel:
            growth[country] = _robust_z(_log_cagr(panel[column]))
    return pd.DataFrame(growth)


def _global_output_factors(panel: pd.DataFrame) -> dict[str, pd.Series]:
    growth = _country_growth_panel(panel)
    ex_uk_members = growth.drop(columns="GBR")
    ex_uk = ex_uk_members.median(axis=1, skipna=True)
    ex_uk[ex_uk_members.notna().sum(axis=1) < 3] = np.nan
    including_uk = growth.median(axis=1, skipna=True)
    including_uk[growth.notna().sum(axis=1) < 3] = np.nan

    total_gdp = {}
    for country in COUNTRIES:
        column = f"MPD_{country}_GDP_MN_2011_INTL_EXT_WB_GROWTH"
        if column in panel:
            total_gdp[country] = pd.to_numeric(panel[column], errors="coerce")
    totals = pd.DataFrame(total_gdp)
    ex_uk_total = totals.drop(columns="GBR").sum(axis=1, min_count=5)
    ex_uk_total[totals.drop(columns="GBR").notna().sum(axis=1) < 5] = np.nan
    including_uk_total = totals.sum(axis=1, min_count=6)
    including_uk_total[totals.notna().sum(axis=1) < 6] = np.nan
    return {
        "countryGrowth": growth,
        "equalWeightExUk": _robust_z(ex_uk),
        "equalWeightIncludingUk": _robust_z(including_uk),
        "aggregateGrowthExUk": _robust_z(_log_cagr(ex_uk_total)),
        "aggregateGrowthIncludingUk": _robust_z(_log_cagr(including_uk_total)),
        "ukAggregateGrowth": _robust_z(_log_cagr(totals["GBR"])),
    }


def _local_proxy_analysis(panel: pd.DataFrame) -> dict[str, Any]:
    factors = _global_output_factors(panel)
    reference = factors["equalWeightExUk"]
    country_growth = factors["countryGrowth"]
    equal_weight_including = factors["equalWeightIncludingUk"]
    include_observations, include_correlation = _correlation(
        _bandpass(equal_weight_including.loc[1700:]),
        _bandpass(reference.loc[1700:]),
    )

    proxies = {
        "ukGdpPerCapita": _proxy_result(country_growth["GBR"], reference, start=1700),
        "ukAggregateGdp": _proxy_result(
            factors["ukAggregateGrowth"],
            factors["aggregateGrowthExUk"],
            start=1820,
        ),
        "ukCpiInflation": _proxy_result(
            _robust_z(_rolling_level(panel["UK_CPI_INFLATION_YOY_PCT_EXT_WB"])),
            reference,
            start=1700,
        ),
        "ukTfp": _proxy_result(
            _robust_z(_rolling_level(panel["UK_BOE_A1_30_TFP_growth"])),
            reference,
            start=1761,
        ),
        "ukLabourProductivity": _proxy_result(
            _robust_z(_log_cagr(panel["UK_BOE_A1_31_Labour_productivity"])),
            reference,
            start=1856,
        ),
        "ukInvestment": _proxy_result(
            _robust_z(_log_cagr(panel["UK_BOE_A1_16_Real_investment"])),
            reference,
            start=1830,
        ),
        "ukSharePrices": _proxy_result(
            _robust_z(_log_cagr(panel["UK_BOE_SHARE_PRICES_INDEX_1962_04_100_EXT_OECD"])),
            reference,
            start=1700,
        ),
        "ukConsolYield": _proxy_result(
            _robust_z(_rolling_level(panel["UK_BOE_CONSOLS_YIELD_PCT_EXT_OECD"])),
            reference,
            start=1703,
        ),
    }
    uk_wave = _bandpass(country_growth["GBR"].loc[1700:])
    global_wave = _bandpass(reference.loc[1700:])
    proxies["ukGdpPerCapita"]["eraBandCorrelations"] = _era_correlations(
        uk_wave,
        global_wave,
        [(1700, 1819), (1820, 1869), (1870, 1913), (1914, 1945), (1946, 1979), (1980, 2024)],
    )
    return {
        "periodBandYears": list(PERIOD_BAND),
        "growthTransform": "10年复合增长率；各国稳健标准化；至少三个非英国经济体的横截面中位数",
        "countryCount": len(country_growth.columns),
        "countries": list(country_growth.columns),
        "globalIncludingVsExcludingUkBandCorrelation": include_correlation,
        "globalIncludingVsExcludingUkBandObservations": include_observations,
        "proxies": proxies,
        "conclusion": "英国 GDP 可作为早期工业化锚点，但其35—70年低频分量与剔除英国后的全球增长并不稳定同相；英国 CPI 与全球实体长波的同步性更弱。",
    }


def _read_bcl_sheet(path: Path, sheet: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet)
    frame = frame.rename(columns={frame.columns[0]: "year"}).set_index("year")
    frame = frame.drop(columns=[column for column in frame.columns if str(column).startswith("Unnamed")], errors="ignore")
    return frame.apply(pd.to_numeric, errors="coerce")


def _read_jst(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path)
    except ValueError:
        return pd.read_stata(path)


def _cross_country_factor(frame: pd.DataFrame, transform: str) -> pd.Series:
    if transform == "growth":
        transformed = frame.apply(_log_cagr)
    elif transform == "inflation":
        transformed = np.log(frame.where(frame > 0)).diff().rolling(10, min_periods=7).mean()
    elif transform == "rolling":
        transformed = frame.rolling(10, min_periods=7).mean()
    else:
        transformed = frame
    standardized = transformed.apply(_robust_z)
    return _robust_z(standardized.median(axis=1, skipna=True))


def _modern_validation(
    panel: pd.DataFrame,
    jst_path: Path | None,
    bcl_path: Path | None,
) -> dict[str, Any]:
    if not jst_path or not bcl_path or not jst_path.exists() or not bcl_path.exists():
        return {
            "available": False,
            "reason": "未同时提供 JST Macrohistory 与 Long-Term Productivity Database 文件。",
        }

    productivity = {
        name: _cross_country_factor(_read_bcl_sheet(bcl_path, sheet), "growth")
        for name, sheet in {
            "gdpPerCapita": "GDP per capita",
            "labourProductivity": "Labor Productivity",
            "tfp": "TFP",
        }.items()
    }
    productivity_core = (productivity["labourProductivity"] + productivity["tfp"]) / 2.0
    productivity_wave = _bandpass(productivity_core)

    jst = _read_jst(jst_path)
    jst["year"] = pd.to_numeric(jst["year"], errors="coerce")

    def jst_factor(column: str, transform: str) -> pd.Series:
        wide = jst.pivot(index="year", columns="iso", values=column).apply(pd.to_numeric, errors="coerce")
        return _cross_country_factor(wide, transform)

    validation_series = {
        "gdpPerCapita": jst_factor("rgdpmad", "growth"),
        "inflation": jst_factor("cpi", "inflation"),
        "investmentShare": jst_factor("iy", "rolling"),
        "equityTotalReturn": jst_factor("eq_tr", "rolling"),
        "housingTotalReturn": jst_factor("housing_tr", "rolling"),
        "bondTotalReturn": jst_factor("bond_tr", "rolling"),
        "longRate": jst_factor("ltrate", "rolling"),
        "publicDebtRatio": jst_factor("debtgdp", "rolling"),
    }
    relationships = {}
    for name, series in validation_series.items():
        relationships[name] = _proxy_result(series, productivity_core, start=1890)

    uk_inflation = _robust_z(_rolling_level(panel["UK_CPI_INFLATION_YOY_PCT_EXT_WB"]))
    uk_vs_global_inflation = _proxy_result(uk_inflation, validation_series["inflation"], start=1870)

    peaks, _ = find_peaks(
        productivity_wave.to_numpy(dtype=float),
        distance=30,
        prominence=float(productivity_wave.std() * 0.35),
    )
    return {
        "available": True,
        "period": [1890, int(productivity_core.dropna().index.max())],
        "productivityCore": "BCL 跨国劳动生产率与 TFP 十年增长因子，不含资产价格",
        "relationships": relationships,
        "ukVsGlobalAdvancedEconomyInflation": uk_vs_global_inflation,
        "productivityPeakCandidates": [int(productivity_wave.index[index]) for index in peaks],
        "warning": "1890年以来只有约2.5个候选长波，滤波相关通常偏高，只能作为机制一致性验证，不能证明固定康波存在。",
    }


def build_analysis(
    *,
    panel_path: Path = PANEL_PATH,
    jst_path: Path | None = None,
    bcl_path: Path | None = None,
) -> dict[str, Any]:
    panel = pd.read_parquet(panel_path)
    return {
        "asOf": "2026-08-12",
        "status": "research_only",
        "longSampleProxyAssessment": _local_proxy_analysis(panel),
        "modernCrossCountryValidation": _modern_validation(panel, jst_path, bcl_path),
        "recommendedArchitecture": {
            "coreIdentification": [
                "跨国实际 GDP 与人均 GDP 的时变权重动态因子",
                "跨国劳动生产率与 TFP",
                "CHAT 技术扩散广度、基础设施渗透率与单位成本下降",
                "1820年以来世界能源消费、能源强度与主导能源份额",
                "投资率、资本深化、世界贸易量与城市化",
            ],
            "financialValidation": [
                "全球长期实际利率",
                "股票、住房、债券与商品价格",
                "私人信用、公共债务、估值与风险溢价",
            ],
            "blockedShortcut": "不得把资产价格放入核心因子后，再用资产价格与核心因子的高相关证明模型有效。",
        },
        "methodRecommendation": "不再使用固定50年正弦或单一带通；采用不规则频率动态因子、35—70年随机周期状态空间、wavelet/multitaper交叉验证、AR(1)红噪声与相位随机化检验，并做逐国剔除和历史截点重算。",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=PANEL_PATH)
    parser.add_argument("--jst", type=Path)
    parser.add_argument("--bcl", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    payload = build_analysis(panel_path=args.panel, jst_path=args.jst, bcl_path=args.bcl)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "status": payload["status"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
