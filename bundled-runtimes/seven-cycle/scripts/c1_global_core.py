"""Build the global real-economy core used by C1 research."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


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
FAMILY_WEIGHTS = {
    "全球产出": 1.0,
    "全球生产率": 1.0,
    "技术扩散": 1.0,
    "资本形成": 0.8,
    "劳动人口": 0.5,
    "全球连接": 0.7,
    "全球能源系统": 0.8,
}
TECHNOLOGY_CLUSTERS = {
    "运输": (
        "railline",
        "railpkm",
        "railtkm",
        "ship_steam",
        "ship_steammotor",
        "vehicle_car",
        "vehicle_com",
        "aviationpkm",
        "aviationtkm",
    ),
    "通信": ("mail", "telegram", "telephone", "radio", "tv", "newspaper"),
    "工业": (
        "elecprod",
        "steel_acidbess",
        "steel_basicbess",
        "steel_bof",
        "steel_eaf",
        "steel_ohf",
        "spindle_mule",
        "spindle_ring",
    ),
    "数字": ("computer", "internetuser", "cellphone", "atm", "pos", "eft", "creditdebit"),
}
MIN_BRIDGE_OVERLAP_YEARS = 15
MIN_BRIDGE_CORRELATION = 0.5


def _row_median(frame: pd.DataFrame) -> pd.Series:
    values = frame.to_numpy(dtype=float, copy=True)
    valid_count = np.isfinite(values).sum(axis=1)
    values[valid_count == 0, 0] = 0.0
    result = pd.Series(
        np.nanmedian(values, axis=1),
        index=frame.index,
        dtype=float,
    )
    result[valid_count == 0] = np.nan
    return result


def robust_z(series: pd.Series) -> pd.Series:
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


def log_cagr(series: pd.Series, years: int = 10) -> pd.Series:
    levels = pd.to_numeric(series, errors="coerce").where(lambda values: values > 0)
    return (np.log(levels) - np.log(levels.shift(years))) / years


def _cross_country_factor(frame: pd.DataFrame, transform: str) -> pd.Series:
    if transform == "growth":
        transformed = frame.apply(log_cagr)
    elif transform == "rolling":
        transformed = frame.rolling(10, min_periods=7).mean()
    else:
        transformed = frame
    standardized = transformed.apply(robust_z)
    factor = robust_z(_row_median(standardized))
    factor[standardized.notna().sum(axis=1) < 3] = np.nan
    return factor


def _global_output(panel: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    per_capita = pd.DataFrame(
        {
            country: pd.to_numeric(
                panel[f"MPD_{country}_GDPPC_2011_INTL_EXT_WB_GROWTH"],
                errors="coerce",
            )
            for country in COUNTRIES
        }
    )
    equal_weight = _cross_country_factor(per_capita, "growth")
    totals = pd.DataFrame(
        {
            country: pd.to_numeric(
                panel[f"MPD_{country}_GDP_MN_2011_INTL_EXT_WB_GROWTH"],
                errors="coerce",
            )
            for country in COUNTRIES
        }
    )
    aggregate_level = totals.sum(axis=1, min_count=6)
    aggregate_growth = robust_z(log_cagr(aggregate_level))
    aggregate_growth[totals.notna().sum(axis=1) < 6] = np.nan
    members = pd.concat([equal_weight.rename("equal"), aggregate_growth.rename("aggregate")], axis=1)
    factor = robust_z(members.mean(axis=1, skipna=True))
    factor[members.notna().sum(axis=1) == 0] = np.nan
    return factor, {
        "source": "Maddison Project Database + World Bank extension",
        "identity": "跨国实际人均GDP十年增长中位数；1820年后叠加多国GDP总量增长",
        "globalScope": True,
        "memberCount": len(COUNTRIES),
    }


def _population(panel: pd.DataFrame) -> tuple[pd.Series, dict[str, Any]]:
    population = pd.DataFrame(
        {
            country: pd.to_numeric(
                panel[f"MPD_{country}_POP_THOUSANDS_EXT_WB_GROWTH"],
                errors="coerce",
            )
            for country in COUNTRIES
        }
    )
    return _cross_country_factor(population, "growth"), {
        "source": "Maddison Project Database + World Bank extension",
        "identity": "跨国人口十年增长中位数",
        "globalScope": True,
        "memberCount": len(COUNTRIES),
    }


def _read_bcl_sheet(path: Path, sheet: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet)
    frame = frame.rename(columns={frame.columns[0]: "year"}).set_index("year")
    frame = frame.drop(
        columns=[column for column in frame.columns if str(column).startswith("Unnamed")],
        errors="ignore",
    )
    return frame.apply(pd.to_numeric, errors="coerce")


def _read_jst(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path)
    except ValueError:
        return pd.read_stata(path)


def _productivity(path: Path) -> tuple[pd.Series, dict[str, Any]]:
    labour = _cross_country_factor(_read_bcl_sheet(path, "Labor Productivity"), "growth")
    tfp = _cross_country_factor(_read_bcl_sheet(path, "TFP"), "growth")
    members = pd.concat([labour.rename("labour"), tfp.rename("tfp")], axis=1)
    factor = robust_z(members.mean(axis=1, skipna=True))
    factor[members.notna().sum(axis=1) < 2] = np.nan
    return factor, {
        "source": "Bergeaud-Cette-Lecat Long-Term Productivity Database v2.7",
        "identity": "跨国劳动生产率与TFP十年增长",
        "globalScope": True,
        "memberCount": 2,
    }


def _world_bank_factor(panel: pd.DataFrame, suffix: str) -> pd.Series:
    wide = pd.DataFrame(
        {
            country: pd.to_numeric(panel[f"WB_{country}_{suffix}"], errors="coerce")
            for country in COUNTRIES
            if f"WB_{country}_{suffix}" in panel
        }
    )
    return _cross_country_factor(wide, "rolling")


def _splice_tail(
    historical: pd.Series,
    extension: pd.Series,
    *,
    minimum_overlap_years: int = MIN_BRIDGE_OVERLAP_YEARS,
    minimum_correlation: float = MIN_BRIDGE_CORRELATION,
) -> tuple[pd.Series, dict[str, Any]]:
    overlap = pd.concat(
        [historical.rename("historical"), extension.rename("extension")],
        axis=1,
    ).dropna()
    correlation = (
        float(overlap.corr().loc["historical", "extension"])
        if len(overlap) >= 3
        else None
    )
    diagnostics = {
        "bridgeOverlapYears": int(len(overlap)),
        "bridgeOverlapCorrelation": (
            round(correlation, 4) if correlation is not None else None
        ),
        "bridgeMinimumOverlapYears": minimum_overlap_years,
        "bridgeMinimumCorrelation": minimum_correlation,
    }
    if (
        len(overlap) < minimum_overlap_years
        or correlation is None
        or not np.isfinite(correlation)
        or correlation < minimum_correlation
    ):
        return historical, {**diagnostics, "bridgeStatus": "rejected"}
    variance = float(overlap["extension"].var())
    slope = float(overlap.cov().loc["historical", "extension"] / variance) if variance > 1e-9 else 1.0
    aligned = overlap["historical"].mean() + slope * (extension - overlap["extension"].mean())
    historical_end = int(historical.dropna().index.max())
    if historical_end in aligned.index and pd.notna(aligned.loc[historical_end]):
        aligned = aligned + float(historical.loc[historical_end] - aligned.loc[historical_end])
    tail = aligned.loc[aligned.index > historical_end]
    combined = pd.concat([historical, tail]).sort_index()
    return combined[~combined.index.duplicated(keep="first")], {
        **diagnostics,
        "bridgeStatus": "research_bridge",
    }


def _jst_factors(
    path: Path,
    panel: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, dict[str, Any], dict[str, Any]]:
    frame = _read_jst(path)
    frame["year"] = pd.to_numeric(frame["year"], errors="coerce")
    investment = frame.pivot(index="year", columns="iso", values="iy").apply(pd.to_numeric, errors="coerce")
    capital_historical = _cross_country_factor(investment, "rolling")
    capital_extension = _world_bank_factor(panel, "GROSS_CAPITAL_FORMATION_PCT_GDP")
    capital, capital_bridge = _splice_tail(capital_historical, capital_extension)

    imports = pd.to_numeric(frame["imports"], errors="coerce")
    exports = pd.to_numeric(frame["exports"], errors="coerce")
    gdp = pd.to_numeric(frame["gdp"], errors="coerce").replace(0.0, np.nan)
    frame["trade_open"] = (imports + exports) / gdp
    trade = frame.pivot(index="year", columns="iso", values="trade_open")
    connection_historical = _cross_country_factor(trade, "rolling")
    connection_extension = _world_bank_factor(panel, "TRADE_PCT_GDP")
    connection, connection_bridge = _splice_tail(
        connection_historical,
        connection_extension,
    )
    return capital, connection, {
        "source": "JST Macrohistory R6 + World Bank WDI",
        "identity": "跨国投资率十年均值；2020年后以世界银行资本形成率桥接",
        "globalScope": True,
        "memberCount": int(investment.shape[1]),
        **capital_bridge,
    }, {
        "source": "JST Macrohistory R6 + World Bank WDI",
        "identity": "跨国进出口占GDP比重十年均值；2020年后以世界银行贸易率桥接",
        "globalScope": True,
        "memberCount": int(trade.shape[1]),
        **connection_bridge,
    }


def _energy_system(path: Path) -> tuple[pd.Series, dict[str, Any]]:
    frame = pd.read_csv(path)
    world = frame.loc[frame["Entity"].eq("World")].set_index("Year")
    source_columns = [
        "Traditional biomass",
        "Coal",
        "Oil",
        "Gas",
        "Nuclear",
        "Hydropower",
        "Wind",
        "Solar",
        "Biofuels",
        "Other renewables",
    ]
    years = pd.Index(
        range(int(world.index.min()), int(world.index.max()) + 1),
        name="year",
    )
    levels = world[source_columns].apply(pd.to_numeric, errors="coerce").reindex(years)
    levels = levels.interpolate(limit_direction="both").clip(lower=0.0)
    total = levels.sum(axis=1, min_count=1)
    commercial = levels.drop(columns="Traditional biomass").sum(axis=1, min_count=1)
    shares = levels.div(total.replace(0.0, np.nan), axis=0)
    transition_speed = shares.diff(10).abs().sum(axis=1, min_count=2) / 10.0
    members = pd.DataFrame(
        {
            "totalGrowth": robust_z(log_cagr(total)),
            "commercialGrowth": robust_z(log_cagr(commercial)),
            "transitionSpeed": robust_z(transition_speed),
        }
    )
    factor = robust_z(_row_median(members))
    factor[members.notna().sum(axis=1) < 2] = np.nan
    return factor, {
        "source": "Our World in Data；Smil (2017)；Energy Institute (2026)",
        "identity": "全球一次能源十年增长、商业能源扩张与能源结构转换速度",
        "globalScope": True,
        "memberCount": len(members.columns),
        "frequency": "1800—1964年按公开基准年插值，1965年后年度数据",
    }


def _technology_column(frame: pd.DataFrame, column: str) -> pd.Series:
    wide = frame.pivot(index="year", columns="country_name", values=column).apply(pd.to_numeric, errors="coerce")
    growth = (np.log1p(wide.where(wide >= 0)).diff(5) / 5.0).apply(robust_z)
    factor = robust_z(_row_median(growth))
    factor[growth.notna().sum(axis=1) < 3] = np.nan
    return factor


def _modern_technology(path: Path) -> pd.Series:
    frame = pd.read_csv(path)
    members = []
    for field in frame["field"].dropna().unique():
        subset = frame.loc[frame["field"].eq(field)]
        wide = subset.pivot(index="year", columns="country", values="value")
        growth = (np.log1p(wide.where(wide >= 0)).diff(5) / 5.0).apply(robust_z)
        factor = robust_z(_row_median(growth))
        factor[growth.notna().sum(axis=1) < 3] = np.nan
        members.append(factor.rename(field))
    modern = pd.concat(members, axis=1)
    factor = robust_z(_row_median(modern))
    factor[modern.notna().sum(axis=1) < 2] = np.nan
    return factor


def _technology(path: Path, modern_path: Path) -> tuple[pd.Series, dict[str, Any]]:
    frame = pd.read_csv(path, low_memory=False)
    cluster_factors = {}
    used = []
    for cluster, columns in TECHNOLOGY_CLUSTERS.items():
        members = []
        for column in columns:
            if column not in frame:
                continue
            factor = _technology_column(frame, column)
            if factor.notna().sum() < 15:
                continue
            members.append(factor.rename(column))
            used.append(column)
        cluster_frame = pd.concat(members, axis=1)
        cluster_factor = robust_z(_row_median(cluster_frame))
        cluster_factor[cluster_frame.notna().sum(axis=1) == 0] = np.nan
        cluster_factors[cluster] = cluster_factor
    clusters = pd.DataFrame(cluster_factors)
    historical = robust_z(_row_median(clusters))
    historical[clusters.notna().sum(axis=1) == 0] = np.nan
    modern = _modern_technology(modern_path)
    factor, bridge = _splice_tail(historical, modern)
    return factor, {
        "source": "Comin-Hobijn CHAT Dataset + World Bank WDI",
        "identity": "运输、通信、工业和数字技术的跨国五年扩散速度；世界银行现代技术序列仅在重叠一致性通过后续接",
        "globalScope": True,
        "memberCount": len(used),
        "clusters": list(cluster_factors),
        **bridge,
    }


def build_global_core_panel(
    panel: pd.DataFrame,
    *,
    bcl_path: Path,
    jst_path: Path,
    chat_path: Path,
    modern_technology_path: Path,
    energy_path: Path,
    start_year: int = 1700,
    end_year: int = 2024,
) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.Series]:
    output, output_meta = _global_output(panel)
    population, population_meta = _population(panel)
    productivity, productivity_meta = _productivity(bcl_path)
    capital, connection, capital_meta, connection_meta = _jst_factors(jst_path, panel)
    technology, technology_meta = _technology(chat_path, modern_technology_path)
    energy, energy_meta = _energy_system(energy_path)
    families = {
        "全球产出": (output, output_meta),
        "全球生产率": (productivity, productivity_meta),
        "技术扩散": (technology, technology_meta),
        "资本形成": (capital, capital_meta),
        "劳动人口": (population, population_meta),
        "全球连接": (connection, connection_meta),
        "全球能源系统": (energy, energy_meta),
    }
    years = pd.Index(range(start_year, end_year + 1), name="year")
    family_panel = pd.DataFrame(
        {name: series.reindex(years) for name, (series, _) in families.items()},
        index=years,
    )
    coverage = []
    for name, (_, metadata) in families.items():
        valid = family_panel[name].dropna()
        coverage.append(
            {
                "family": name,
                "start": int(valid.index.min()),
                "end": int(valid.index.max()),
                "weight": FAMILY_WEIGHTS[name],
                **metadata,
            }
        )
    weights = pd.Series(FAMILY_WEIGHTS, dtype=float)
    return family_panel, coverage, weights
