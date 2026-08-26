#!/usr/bin/env python3
"""Build governed, browser-ready research products from approved local inputs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import re
import shutil
from typing import Any, Iterable
from urllib.request import urlretrieve

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
import yaml

try:
    from scripts.cycle_robustness_core import (
        annual_category,
        butterworth_component,
        gaussian_fft_component,
        infer_value_type,
        preprocess_series,
        regularize_series,
    )
    from scripts.indicator_cycle_contribution import (
        apply_cross_filter_gain_calibration,
        build_cross_filter_indicator_cycle_contribution,
        summarize_indicator_cycle_contributions,
    )
    from scripts.indicator_cycle_realtime_confirmation import (
        build_peer_shared_error_pools,
        build_realtime_indicator_confirmation,
        build_realtime_indicator_peer_pool_input,
    )
    from scripts.research_track_forecast import build_track_forecast
    from scripts.research_c1_long_wave_validation import build_validation as build_c1_validation
except ModuleNotFoundError:
    from cycle_robustness_core import (
        annual_category,
        butterworth_component,
        gaussian_fft_component,
        infer_value_type,
        preprocess_series,
        regularize_series,
    )
    from indicator_cycle_contribution import (
        apply_cross_filter_gain_calibration,
        build_cross_filter_indicator_cycle_contribution,
        summarize_indicator_cycle_contributions,
    )
    from indicator_cycle_realtime_confirmation import (
        build_peer_shared_error_pools,
        build_realtime_indicator_confirmation,
        build_realtime_indicator_peer_pool_input,
    )
    from research_track_forecast import build_track_forecast
    from research_c1_long_wave_validation import build_validation as build_c1_validation


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DATA_DIR = PROJECT_ROOT / "web" / "public" / "data"
RAW_PUBLIC_DIR = PROJECT_ROOT / "data" / "raw" / "web_public"
C4_FORECAST_FALLBACK = PROJECT_ROOT / "output" / "c4_forecast_prototype_2026-07-19.json"
C4_FORECAST_REPRODUCIBLE = PROJECT_ROOT / "output" / "c4_forecast_reproducible_latest.json"
C4_REALTIME_FALLBACK = PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
C4_REALTIME_BRIDGE = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
C5_LIQUIDITY_STATE = PROJECT_ROOT / "output" / "c5_liquidity_state_research.json"
C7_RISK_APPETITE_STATE = PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json"
CURRENT_PANEL_REFRESH = PROJECT_ROOT / "output" / "research_current_panel_refresh.json"
ASSET_RETURNS_REFRESH = PROJECT_ROOT / "output" / "asset_returns_current_refresh.json"
ASSET_CYCLE_FORECAST = PROJECT_ROOT / "output" / "asset_cycle_state_forecast.json"
C4_ASSET_STATISTICS_CURRENT = PROJECT_ROOT / "output" / "c4_asset_statistics_current.json"
C5_C7_ASSET_ASSOCIATION = PROJECT_ROOT / "output" / "c5_c7_asset_association.json"
C2_REGIME_REFACTOR = PROJECT_ROOT / "output" / "c2_regime_refactor.json"
C3_REGIME_REFACTOR = PROJECT_ROOT / "output" / "c3_regime_refactor.json"

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
WORLD_BANK_PINK_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "5d903e848db1d1b83e0ec8f744e55570-0350012021/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)


@dataclass(frozen=True, slots=True)
class TrackSpec:
    track_id: str
    label: str
    category: str
    group: str
    unit: str
    source: str
    source_code: str
    transform: str
    frequency: str = "M"
    proxy_status: str = "direct"
    caveat: str | None = None


DEFAULT_TRACK_IDS = [
    "us_pmi",
    "us_ppi",
    "us_cpi",
    "us_policy_rate",
    "dxy",
    "sp500",
    "nasdaq",
    "us10y",
    "comex_gold",
    "wti",
]

CYCLE_IDENTIFICATION_TRACK_IDS = [
    "us_pmi",
    "us_industrial_production",
    "us_cpi",
    "us_ppi",
    "us_policy_rate",
    "us_term_spread",
    "us_nfci",
    "dxy",
    "sp500",
    "global_commodity",
]

CORE_TRACK_IDS = list(
    dict.fromkeys(DEFAULT_TRACK_IDS + CYCLE_IDENTIFICATION_TRACK_IDS)
)

DEFAULT_TRACK_SPECS = {
    "us_pmi": TrackSpec(
        track_id="us_pmi",
        label="美国 PMI（新订单代理）",
        category="生产与增长",
        group="economic",
        unit="百万美元",
        source="FRED 制造商新订单",
        source_code="AMTMNO",
        transform="log_change",
        proxy_status="proxy",
        caveat="公开可复核的美国制造业 PMI 长序列不可直接入库，使用 FRED 制造商新订单作为先行代理；服务业 PMI 保留在扩展轨道。",
    ),
    "us_ppi": TrackSpec(
        track_id="us_ppi",
        label="美国 PPI",
        category="价格与通胀",
        group="economic",
        unit="指数",
        source="FRED",
        source_code="PPIACO",
        transform="log_change",
    ),
    "us_cpi": TrackSpec(
        track_id="us_cpi",
        label="美国 CPI",
        category="价格与通胀",
        group="economic",
        unit="指数",
        source="FRED",
        source_code="CPIAUCSL",
        transform="log_change",
    ),
    "us_policy_rate": TrackSpec(
        track_id="us_policy_rate",
        label="美国政策利率",
        category="利率与流动性",
        group="economic",
        unit="%",
        source="FRED",
        source_code="FEDFUNDS",
        transform="diff",
    ),
    "us_industrial_production": TrackSpec(
        track_id="us_industrial_production",
        label="美国工业生产",
        category="生产与增长",
        group="economic",
        unit="2017=100",
        source="FRED",
        source_code="INDPRO",
        transform="log_change",
    ),
    "us_term_spread": TrackSpec(
        track_id="us_term_spread",
        label="美国 10年-2年期限利差",
        category="利率与信用",
        group="economic",
        unit="百分点",
        source="FRED",
        source_code="T10Y2Y",
        transform="diff",
        caveat="使用月内日度均值，曲面展示利差的月度变化，不把倒挂水平直接解释为资产收益。",
    ),
    "us_nfci": TrackSpec(
        track_id="us_nfci",
        label="美国金融条件（NFCI）",
        category="信用与金融条件",
        group="economic",
        unit="指数点",
        source="FRED / 芝加哥联储",
        source_code="NFCI",
        transform="diff",
        caveat="NFCI为美国金融条件综合指数；这里只使用月度变化，不能代表全球信用条件。",
    ),
    "dxy": TrackSpec(
        track_id="dxy",
        label="美元指数",
        category="外汇",
        group="market",
        unit="指数",
        source="FRED",
        source_code="DTWEXBGS",
        transform="log_change",
    ),
    "sp500": TrackSpec(
        track_id="sp500",
        label="标普 500",
        category="海外股票",
        group="market",
        unit="点",
        source="FRED",
        source_code="SP500",
        transform="log_change",
    ),
    "nasdaq": TrackSpec(
        track_id="nasdaq",
        label="纳斯达克指数",
        category="海外股票",
        group="market",
        unit="点",
        source="FRED",
        source_code="NASDAQCOM",
        transform="log_change",
    ),
    "us10y": TrackSpec(
        track_id="us10y",
        label="美债 10 年收益率",
        category="利率与债券",
        group="market",
        unit="%",
        source="FRED",
        source_code="DGS10",
        transform="diff",
    ),
    "comex_gold": TrackSpec(
        track_id="comex_gold",
        label="COMEX 黄金期货",
        category="贵金属",
        group="market",
        unit="美元/盎司",
        source="Yahoo Finance",
        source_code="GC=F / US_COMEX_GOLD_FUT_LEVEL",
        transform="log_change",
        proxy_status="direct",
        caveat="COMEX 黄金期货连续合约月末收盘价；连续合约仍可能包含换月口径影响。",
    ),
    "wti": TrackSpec(
        track_id="wti",
        label="WTI 原油",
        category="能源",
        group="market",
        unit="美元/桶",
        source="FRED",
        source_code="DCOILWTICO",
        transform="log_change",
    ),
    "global_commodity": TrackSpec(
        track_id="global_commodity",
        label="全球综合商品指数",
        category="综合商品",
        group="market",
        unit="2016=100",
        source="FRED / IMF",
        source_code="PALLFNFINDEXM",
        transform="log_change",
        caveat="IMF全球全部商品价格指数，覆盖能源、金属与农产品；用于替代单一黄金或原油轨道观察商品总周期。",
    ),
}

CYCLE_CENTERS = {
    "C1": 600.0,
    "C2": 200.0,
    "C3": 100.0,
    "C4": 42.0,
    "C5": 20.0,
    "C6": 12.0,
    "C7": 6.0,
}
ANNUAL_CONTRIBUTION_PERIODS = {
    "C1": 50.0,
    "C2": 200.0 / 12.0,
    "C3": 100.0 / 12.0,
}
ANNUAL_CATEGORY_LABELS = {
    "real_per_capita": "人均实际增长",
    "real_aggregate": "实际经济总量",
    "demography": "人口",
    "prices_commodities": "价格与商品",
    "rates_credit": "利率与信用",
    "money_credit": "货币与信用",
    "labor_productivity": "劳动力与生产率",
    "real_activity": "实际活动",
    "markets": "市场价格",
    "fiscal": "财政",
    "external": "对外部门",
}
COUNTRY_LABELS = {
    "AUS": "澳大利亚",
    "BRA": "巴西",
    "CAN": "加拿大",
    "CHN": "中国",
    "DEU": "德国",
    "ESP": "西班牙",
    "FRA": "法国",
    "GBR": "英国",
    "IND": "印度",
    "ITA": "意大利",
    "JPN": "日本",
    "KOR": "韩国",
    "NLD": "荷兰",
    "SWE": "瑞典",
    "USA": "美国",
}


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (pd.Timestamp, date)):
        return pd.Timestamp(value).strftime("%Y-%m")
    return value


def _json_array(values: Iterable[object]) -> list[object]:
    return [_json_value(value) for value in values]


def _json_structure(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_structure(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_structure(item) for item in value]
    return _json_value(value)


def _annual_indicator_label(column: str) -> str:
    match = re.match(r"MPD_([A-Z]{3})_(GDPPC|GDP_MN|POP)_", column)
    if match:
        country = COUNTRY_LABELS.get(match.group(1), match.group(1))
        metric = {
            "GDPPC": "人均GDP增长",
            "GDP_MN": "实际GDP增长",
            "POP": "人口增长",
        }[match.group(2)]
        return f"{country} · {metric}"
    return column.removeprefix("UK_BOE_").replace("_", " ")


def _merge_annual_contribution_results(
    results: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if len(results) != 2:
        return None
    eligible = sorted(set(results[0]["eligibleCycles"]) & set(results[1]["eligibleCycles"]))
    if not eligible:
        return None
    point_values = {
        cycle_id: float(
            np.median(
                [result["current"]["components"][cycle_id]["pointContribution"] for result in results]
            )
        )
        for cycle_id in eligible
    }
    absolute_total = sum(abs(value) for value in point_values.values())
    components = {}
    direction_agreements = []
    stable_components = 0
    for cycle_id in eligible:
        method_components = [result["current"]["components"][cycle_id] for result in results]
        signs = [np.sign(row["pointContribution"]) for row in method_components]
        preprocessing_direction_agreement = bool(signs[0] == signs[1])
        direction_agreements.append(preprocessing_direction_agreement)
        filter_rows = [row.get("filterRobustness", {}) for row in method_components]
        filter_direction_agreement = all(
            row.get("directionAgreement") is True for row in filter_rows
        )
        stable = (
            preprocessing_direction_agreement
            and filter_direction_agreement
            and all(row.get("status") == "stable" for row in filter_rows)
        )
        if stable:
            stable_components += 1
        point = point_values[cycle_id]
        components[cycle_id] = {
            "pointContribution": point,
            "absoluteShare": abs(point) / absolute_total if absolute_total > 1e-12 else 0.0,
            "signedShare": point / absolute_total if absolute_total > 1e-12 else 0.0,
            "slope3": float(np.median([row["slope3"] for row in method_components])),
            "varianceShare120": float(
                np.median([row["varianceShare120"] for row in method_components])
            ),
            "coefficient": float(np.median([row["coefficient"] for row in method_components])),
            "filterRobustness": {
                "status": "stable" if stable else "weak",
                "primaryFilter": "gaussian_fft",
                "comparisonFilter": "butterworth_zero_phase",
                "directionAgreement": (
                    preprocessing_direction_agreement and filter_direction_agreement
                ),
                "preprocessingDirectionAgreement": preprocessing_direction_agreement,
                "pathCorrelation": float(
                    np.nanmedian([row.get("pathCorrelation") for row in filter_rows])
                ),
                "relativePointDifference": float(
                    np.nanmedian([row.get("relativePointDifference") for row in filter_rows])
                ),
                "absoluteShareDifference": float(
                    np.nanmedian([row.get("absoluteShareDifference") for row in filter_rows])
                ),
                "varianceShareDifference": float(
                    np.nanmedian([row.get("varianceShareDifference") for row in filter_rows])
                ),
            },
        }
    quality = (
        "stable"
        if stable_components == len(eligible)
        else "weak"
    )
    reconstruction_r2 = float(
        np.median([result["diagnostics"]["reconstructionR2"] for result in results])
    )
    holdout_r2 = float(
        np.median([result["diagnostics"]["holdoutReconstructionR2"] for result in results])
    )
    residual_variance = float(
        np.median([result["diagnostics"]["residualVarianceShare120"] for result in results])
    )
    indicator_value = float(np.median([result["current"]["indicatorValue"] for result in results]))
    baseline = float(np.median([result["current"]["baseline"] for result in results]))
    cycle_total = sum(point_values.values())
    residual = indicator_value - baseline - cycle_total
    primary_model_quality = (
        "stable"
        if all(
            result.get("filterRobustness", {}).get("primaryModelQuality")
            == "stable"
            for result in results
        )
        else "weak"
    )
    comparison_model_quality = (
        "stable"
        if all(
            result.get("filterRobustness", {}).get("comparisonModelQuality")
            == "stable"
            for result in results
        )
        else "weak"
    )
    return {
        "status": "retrospective_diagnostic",
        "quality": quality,
        "method": "annual_hp100_and_linear_detrend_consensus",
        "eligibleCycles": eligible,
        "excludedCycles": [],
        "current": {
            "date": min(result["current"]["date"] for result in results),
            "indicatorValue": indicator_value,
            "baseline": baseline,
            "cycleTotal": cycle_total,
            "residual": residual,
            "conservationError": 0.0,
            "dominantCycle": max(point_values, key=lambda cycle_id: abs(point_values[cycle_id])),
            "components": components,
        },
        "diagnostics": {
            "fitStart": max(result["diagnostics"]["fitStart"] for result in results),
            "fitEnd": min(result["diagnostics"]["fitEnd"] for result in results),
            "fitObservations": min(result["diagnostics"]["fitObservations"] for result in results),
            "edgeTrimMonths": max(result["diagnostics"]["edgeTrimMonths"] for result in results),
            "selectedAlpha": float(np.median([result["diagnostics"]["selectedAlpha"] for result in results])),
            "reconstructionR2": reconstruction_r2,
            "holdoutReconstructionR2": holdout_r2,
            "coefficientSignAgreement": float(np.mean(direction_agreements)),
            "residualVarianceShare120": residual_variance,
        },
        "filterRobustness": {
            "status": quality,
            "primaryFilter": "gaussian_fft",
            "comparisonFilter": "butterworth_zero_phase",
            "primaryModelQuality": primary_model_quality,
            "comparisonModelQuality": comparison_model_quality,
            "stableCycles": stable_components,
            "comparableCycles": len(eligible),
            "directionAgreementCycles": sum(direction_agreements),
        },
        "caveat": "年频长周期贡献同时要求HP(100)/线性去趋势方向一致，以及Gaussian FFT/Butterworth滤波复核达标；任一条件失败均标记为偏弱。",
    }


def _annual_indicator_contribution_study() -> dict[str, Any]:
    panel = pd.read_parquet(PROJECT_ROOT / "data" / "research_input_annual_long.parquet")
    metadata = pd.read_csv(PROJECT_ROOT / "output" / "research_input_annual_long_selection.csv")
    metadata = metadata.loc[metadata["status"].eq("selected")].set_index("column")
    pending_tracks: list[dict[str, Any]] = []
    for ordinal, column in enumerate(panel.columns, start=1):
        regular = regularize_series(panel[column], "A", 80)
        if regular is None:
            continue
        value_type = (
            str(metadata.loc[column, "value_type"])
            if column in metadata.index
            else infer_value_type(column)
        )
        results = []
        for method in ("hp_100", "linear_detrend"):
            standardized = preprocess_series(
                regular,
                value_type=value_type,
                frequency="A",
                method=method,
            )
            if standardized is None:
                continue
            gaussian_components = {
                cycle_id: gaussian_fft_component(standardized, period)
                for cycle_id, period in ANNUAL_CONTRIBUTION_PERIODS.items()
            }
            butterworth_components = {
                cycle_id: butterworth_component(standardized, period)
                for cycle_id, period in ANNUAL_CONTRIBUTION_PERIODS.items()
            }
            result = build_cross_filter_indicator_cycle_contribution(
                standardized,
                gaussian_components,
                butterworth_components,
                periods=ANNUAL_CONTRIBUTION_PERIODS,
                minimum_observations=40,
                primary_filter="gaussian_fft",
                comparison_filter="butterworth_zero_phase",
            )
            if result.get("status") == "retrospective_diagnostic":
                results.append(result)
        if len(results) != 2:
            continue
        pending_tracks.append(
            {
                "ordinal": ordinal,
                "column": column,
                "results": results,
            }
        )
    calibration_tracks = [
        {"cycleContribution": result}
        for pending in pending_tracks
        for result in pending["results"]
    ]
    gain_calibration = apply_cross_filter_gain_calibration(calibration_tracks)
    tracks: list[dict[str, Any]] = []
    for pending in pending_tracks:
        column = pending["column"]
        merged = _merge_annual_contribution_results(pending["results"])
        if merged is None:
            continue
        category_key = annual_category(column)
        tracks.append(
            {
                "id": f"annual_{pending['ordinal']:03d}",
                "label": _annual_indicator_label(column),
                "category": ANNUAL_CATEGORY_LABELS.get(category_key, category_key),
                "group": "economic",
                "cycleContribution": merged,
            }
        )
    study = summarize_indicator_cycle_contributions(
        tracks,
        cycle_ids=("C1", "C2", "C3"),
    )
    return {
        "status": "annual_long_history_frequency_contribution_study",
        "frequency": "A",
        "asOf": str(panel.index.max()),
        "trackCount": len(tracks),
        "method": "HP(100)与线性去趋势双口径，并对Gaussian FFT与Butterworth双滤波交叉复核；全部门槛通过才标记较稳定。",
        "crossFilterGainCalibration": gain_calibration,
        "cycles": study["cycles"],
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _normalize_as_of(value: date | str | pd.Timestamp | None) -> pd.Timestamp:
    timestamp = pd.Timestamp(value or date.today())
    return timestamp.to_period("M").to_timestamp("M")


def _month_gap(older: str | pd.Timestamp, newer: pd.Timestamp) -> int:
    older_period = pd.Period(pd.Timestamp(older), freq="M")
    newer_period = pd.Period(newer, freq="M")
    return max(0, newer_period.ordinal - older_period.ordinal)


def _refresh_public_sources() -> None:
    RAW_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    for series_id in (
        "CPIAUCSL",
        "PPIACO",
        "FEDFUNDS",
        "DTWEXBGS",
        "SP500",
        "NASDAQCOM",
        "DGS10",
        "DCOILWTICO",
        "AMTMNO",
        "VIXCLS",
        "NFCI",
        "BAA",
        "AAA",
        "INDPRO",
        "T10Y2Y",
        "PALLFNFINDEXM",
    ):
        urlretrieve(
            FRED_URL.format(series_id=series_id),
            RAW_PUBLIC_DIR / f"fred_{series_id}.csv",
        )
    urlretrieve(WORLD_BANK_PINK_URL, RAW_PUBLIC_DIR / "world_bank_pink_monthly.xlsx")


def _monthly(
    series: pd.Series,
    aggregation: str = "last",
    *,
    as_of: pd.Timestamp,
) -> pd.Series:
    series = pd.to_numeric(series, errors="coerce")
    series.index = pd.to_datetime(series.index)
    series = series.sort_index().loc[:as_of]
    if aggregation == "mean":
        return series.resample("ME").mean()
    return series.resample("ME").last()


def _fred_series(series_id: str, *, as_of: pd.Timestamp) -> pd.Series:
    path = RAW_PUBLIC_DIR / f"fred_{series_id}.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    value_columns = [column for column in frame.columns if column != "observation_date"]
    if len(value_columns) != 1:
        raise ValueError(f"Unexpected FRED shape for {series_id}")
    series = frame.set_index("observation_date")[value_columns[0]].replace(".", np.nan)
    aggregation = (
        "mean"
        if series_id in {"FEDFUNDS", "DGS10", "DCOILWTICO", "T10Y2Y", "NFCI"}
        else "last"
    )
    return _monthly(series, aggregation, as_of=as_of)


def _world_bank_gold(*, as_of: pd.Timestamp) -> pd.Series:
    path = RAW_PUBLIC_DIR / "world_bank_pink_monthly.xlsx"
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_excel(path, sheet_name="Monthly Prices", header=4)
    date_column = frame.columns[0]
    gold_column = next(column for column in frame.columns if str(column).strip() == "Gold")
    dates = pd.to_datetime(
        frame[date_column].astype(str).str.replace("M", "-", regex=False),
        errors="coerce",
    )
    values = pd.to_numeric(frame[gold_column], errors="coerce")
    series = pd.Series(values.to_numpy(), index=dates).dropna()
    return _monthly(series, "last", as_of=as_of)


def _default_series(panel: pd.DataFrame, *, as_of: pd.Timestamp) -> dict[str, pd.Series]:
    result = {
        "us_pmi": _fred_series("AMTMNO", as_of=as_of)
    }
    for track_id, spec in DEFAULT_TRACK_SPECS.items():
        if track_id == "us_pmi":
            continue
        if track_id == "comex_gold":
            gold_column = "US_COMEX_GOLD_FUT_LEVEL"
            if gold_column in panel and panel[gold_column].notna().any():
                result[track_id] = _monthly(panel[gold_column], as_of=as_of)
            else:
                result[track_id] = _world_bank_gold(as_of=as_of)
        else:
            result[track_id] = _fred_series(spec.source_code, as_of=as_of)
    return result


def _default_track_specs(panel: pd.DataFrame) -> dict[str, TrackSpec]:
    specs = dict(DEFAULT_TRACK_SPECS)
    gold_column = "US_COMEX_GOLD_FUT_LEVEL"
    if gold_column not in panel or not panel[gold_column].notna().any():
        specs["comex_gold"] = TrackSpec(
            track_id="comex_gold",
            label="黄金现货代理",
            category="贵金属",
            group="market",
            unit="美元/盎司",
            source="World Bank Pink Sheet",
            source_code="Gold",
            transform="log_change",
            proxy_status="proxy",
            caveat="COMEX连续合约直接轨道不可用，明确降级为世界银行月度黄金现货代理。",
        )
    return specs


def _change(series: pd.Series, transform: str) -> pd.Series:
    if transform == "log_change":
        positive = series.where(series > 0)
        return np.log(positive).diff() * 100.0
    if transform == "pct_change":
        return series.pct_change(fill_method=None) * 100.0
    if transform == "percent_value":
        return series.astype(float)
    return series.diff()


def _rolling_z(series: pd.Series) -> pd.Series:
    rolling = series.rolling(120, min_periods=36)
    mean = rolling.mean()
    std = rolling.std(ddof=0).replace(0, np.nan)
    return ((series - mean) / std).clip(-4.0, 4.0)


def _bandpass(series: pd.Series, period: float) -> pd.Series:
    values = series.interpolate(limit_direction="both").to_numpy(dtype=float)
    if len(values) < max(36, int(period * 1.35)):
        return pd.Series(np.nan, index=series.index)
    short_sigma = max(1.0, period / 10.0)
    long_sigma = max(short_sigma + 0.5, period / 3.0)
    short = gaussian_filter1d(values, sigma=short_sigma, mode="nearest")
    long = gaussian_filter1d(values, sigma=long_sigma, mode="nearest")
    return pd.Series(short - long, index=series.index)


def _cycle_components(standardized: pd.Series) -> dict[str, pd.Series]:
    return {
        cycle_id: _bandpass(standardized, center)
        for cycle_id, center in CYCLE_CENTERS.items()
    }


def _gaussian_fft_cycle_components(standardized: pd.Series) -> dict[str, pd.Series]:
    filled = standardized.interpolate(limit_direction="both")
    if int(filled.notna().sum()) < 36:
        return {
            cycle_id: pd.Series(np.nan, index=standardized.index)
            for cycle_id in CYCLE_CENTERS
        }
    return {
        cycle_id: gaussian_fft_component(filled, center)
        for cycle_id, center in CYCLE_CENTERS.items()
    }


def _butterworth_cycle_components(standardized: pd.Series) -> dict[str, pd.Series]:
    filled = standardized.interpolate(limit_direction="both")
    if int(filled.notna().sum()) < 36:
        return {
            cycle_id: pd.Series(np.nan, index=standardized.index)
            for cycle_id in CYCLE_CENTERS
        }
    return {
        cycle_id: butterworth_component(filled, center)
        for cycle_id, center in CYCLE_CENTERS.items()
    }


def _stack(components: dict[str, pd.Series], cycle_ids: Iterable[str]) -> pd.Series:
    selected = pd.concat([components[cycle_id] for cycle_id in cycle_ids], axis=1)
    count = selected.notna().sum(axis=1)
    stacked = selected.mean(axis=1, skipna=True).where(count > 0)
    scale = stacked.rolling(120, min_periods=36).std(ddof=0).replace(0, np.nan)
    return (stacked / scale).clip(-4.0, 4.0)


def _phase_name(angle: float) -> str:
    normalized = angle % 360.0
    if normalized < 90:
        return "复苏"
    if normalized < 180:
        return "扩张"
    if normalized < 270:
        return "放缓"
    return "收缩"


def _diagnostic_direction(level: float, slope: float) -> str:
    if level >= 0 and slope >= 0:
        return "上行增强"
    if level >= 0 and slope < 0:
        return "高位放缓"
    if level < 0 and slope >= 0:
        return "低位修复"
    return "下行增强"


def _diagnostic_standardize(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    rolling = series.rolling(window, min_periods=min_periods)
    center = rolling.median()
    scale = (series - center).abs().rolling(window, min_periods=min_periods).median()
    robust_scale = scale * 1.4826
    fallback_scale = rolling.std(ddof=0)
    scale = robust_scale.where(robust_scale > 1e-8, fallback_scale).replace(0, np.nan)
    return ((series - center) / scale).clip(-4.0, 4.0)


def _diagnostic_member(series: pd.Series, mode: str, direction: float = 1.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if mode == "log_change":
        numeric = np.log(numeric.where(numeric > 0)).diff()
    elif mode == "diff":
        numeric = numeric.diff()
    elif mode == "pct_change":
        numeric = numeric.pct_change(fill_method=None)
    return numeric * direction


def _diagnostic_payload(
    *,
    cycle_id: str,
    frequency: str,
    panel: pd.DataFrame,
    families: dict[str, list[tuple[str, str, float]]],
    candidate_periods: list[float],
    state_span: int,
    slope_lag: int,
    model_rebuild: dict[str, Any],
    blockers: list[str],
    unlock_conditions: list[str],
) -> dict[str, Any]:
    family_factors: list[pd.Series] = []
    family_coverage: list[dict[str, Any]] = []
    standardize_window = 40 if frequency == "A" else 60
    min_periods = 18 if frequency == "A" else 30
    for family, definitions in families.items():
        members: list[pd.Series] = []
        used: list[str] = []
        for column, mode, direction in definitions:
            if column not in panel:
                continue
            transformed = _diagnostic_member(panel[column], mode, direction)
            standardized = _diagnostic_standardize(
                transformed,
                window=standardize_window,
                min_periods=min_periods,
            )
            if standardized.notna().sum() < min_periods:
                continue
            members.append(standardized.rename(column))
            used.append(column)
        if not members:
            continue
        member_frame = pd.concat(members, axis=1)
        factor = member_frame.mean(axis=1, skipna=True)
        factor.name = family
        family_factors.append(factor)
        family_coverage.append(
            {
                "family": family,
                "members": used,
                "start": _json_value(factor.first_valid_index()),
                "end": _json_value(factor.last_valid_index()),
                "observations": int(factor.notna().sum()),
            }
        )
    if not family_factors:
        raise ValueError(f"No diagnostic families available for {cycle_id}")
    family_frame = pd.concat(family_factors, axis=1)
    family_count = family_frame.notna().sum(axis=1)
    composite = family_frame.mean(axis=1, skipna=True).where(family_count >= 2)
    start = composite.first_valid_index()
    end = composite.last_valid_index()
    if start is None or end is None:
        raise ValueError(f"Diagnostic composite unavailable for {cycle_id}")
    composite = composite.loc[start:end]
    family_frame = family_frame.reindex(composite.index)
    state = composite.ewm(span=state_span, adjust=False, min_periods=max(3, state_span // 2)).mean()
    slope = state.diff(slope_lag)
    disagreement = family_frame.std(axis=1, ddof=0).rolling(
        max(3, state_span), min_periods=max(2, state_span // 2)
    ).mean()
    candidate_bands = [
        {
            "period": period,
            "values": _json_array(_bandpass(composite, period)),
        }
        for period in candidate_periods
    ]
    band_frame = pd.concat(
        [_bandpass(composite, period).rename(str(period)) for period in candidate_periods],
        axis=1,
    )
    candidate_consensus = band_frame.median(axis=1, skipna=True)
    candidate_dispersion = band_frame.std(axis=1, ddof=0)
    latest_level = float(state.dropna().iloc[-1])
    latest_slope = float(slope.dropna().iloc[-1])
    latest_disagreement = float(disagreement.dropna().iloc[-1]) if not disagreement.dropna().empty else 1.0
    diagnostic_confidence = float(
        np.clip(0.35 + 0.08 * len(family_factors) - 0.12 * latest_disagreement, 0.2, 0.78)
    )
    dates = [
        str(index) if frequency == "A" else pd.Timestamp(index).strftime("%Y-%m")
        for index in composite.index
    ]
    return {
        "cycleId": cycle_id,
        "status": "research_diagnostic",
        "publicationStatus": "blocked",
        "frequency": frequency,
        "dates": dates,
        "composite": _json_array(composite),
        "directionalState": _json_array(state),
        "slope": _json_array(slope),
        "familyDisagreement": _json_array(disagreement),
        "candidateBands": candidate_bands,
        "candidateConsensus": _json_array(candidate_consensus),
        "candidateDispersion": _json_array(candidate_dispersion),
        "familyCoverage": family_coverage,
        "current": {
            "date": dates[-1],
            "level": _json_value(latest_level),
            "slope": _json_value(latest_slope),
            "direction": _diagnostic_direction(latest_level, latest_slope),
            "diagnosticConfidence": _json_value(diagnostic_confidence),
            "familyDisagreement": _json_value(latest_disagreement),
        },
        "modelRebuild": model_rebuild,
        "blockers": blockers,
        "unlockConditions": unlock_conditions,
        "caveat": "方向性状态可用于研究提示，但不改变正式发布门槛，也不作为资产归因周期。",
    }


def _direction_publication_payload(
    cycle_id: str,
    diagnostic: dict[str, Any],
) -> dict[str, Any] | None:
    long_panel = diagnostic.get("longPanel")
    if long_panel:
        checks = {
            "direction_model_validated": long_panel["status"]
            == "directionally_predictable",
            "family_ablation_validated": long_panel.get(
                "familyAblation", {}
            ).get("status")
            == "passed_limited",
            "partial_nowcast_validated": long_panel["partialNowcast"]["validation"][
                "status"
            ]
            == "passed_limited",
        }
        horizons = []
        for forecast in long_panel["currentForecasts"]:
            horizon = int(forecast["horizonYears"])
            validation = long_panel["validation"][f"{horizon}y"]
            checks[f"{horizon}y_accuracy"] = validation["accuracy"] >= 0.65
            checks[f"{horizon}y_brier"] = (
                validation["brier"] < validation["baseBrier"]
            )
            checks[f"{horizon}y_country_holdout"] = (
                validation["leaveCountryOut2000Plus"]["accuracy"] >= 0.65
            )
            horizons.append(
                {
                    "label": f"{horizon}年",
                    "months": horizon * 12,
                    "probability": forecast["probabilityUp"],
                    "outcome": "上行",
                    "accuracy": validation["accuracy"],
                    "qualified": all(
                        checks[key]
                        for key in (
                            f"{horizon}y_accuracy",
                            f"{horizon}y_brier",
                            f"{horizon}y_country_holdout",
                        )
                    ),
                }
            )
        qualified = all(checks.values())
        current_forecast = long_panel["currentForecasts"][0]
        return {
            "status": "limited" if qualified else "blocked",
            "layer": "factor_direction_probability",
            "badgeLabel": "因子方向可用" if qualified else "因子方向阻断",
            "label": "1–3年因子方向概率",
            "asOf": current_forecast.get(
                "asOfPeriod",
                str(current_forecast["asOfYear"]),
            ),
            "currentLabel": current_forecast["direction"],
            "horizons": horizons,
            "exactCycleStatus": diagnostic["publicationStatus"],
            "assetForecastStatus": long_panel["governance"].get(
                "assetForecastStatus",
                "blocked",
            ),
            "independentOutcomeStatus": long_panel.get(
                "independentOutcomeValidation", {}
            ).get("status", "failed"),
            "gate": {
                "passed": qualified,
                "checks": checks,
                "reasonCodes": [
                    name for name, passed in checks.items() if not passed
                ],
            },
            "caveat": long_panel["publishableClaim"],
        }

    liquidity = diagnostic.get("liquidityState")
    if cycle_id == "C5" and liquidity:
        checks = {
            "state_model_validated": liquidity["status"]
            == "state_direction_predictable",
            "3m_validated": liquidity["validation"]["3m"]["qualified"],
            "6m_validated": liquidity["validation"]["6m"]["qualified"],
            "12m_validated": liquidity["validation"]["12m"]["qualified"],
        }
        qualified = all(checks.values())
        horizons = [
            {
                "label": f"{forecast['horizonMonths']}个月",
                "months": forecast["horizonMonths"],
                "probability": max(
                    forecast["probabilityUp"],
                    forecast["probabilityDown"],
                ),
                "outcome": (
                    "状态上行"
                    if forecast["probabilityUp"] >= forecast["probabilityDown"]
                    else "状态下行"
                ),
                "accuracy": liquidity["validation"][
                    f"{forecast['horizonMonths']}m"
                ]["accuracy"],
                "qualified": forecast["qualified"],
            }
            for forecast in liquidity["currentForecasts"]
            if forecast["qualified"]
        ]
        return {
            "status": "limited" if qualified else "blocked",
            "layer": "state_direction_probability",
            "badgeLabel": "状态可用" if qualified else "状态阻断",
            "label": "3–12个月状态方向",
            "asOf": liquidity["current"]["date"],
            "currentLabel": liquidity["current"]["regime"],
            "horizons": horizons,
            "exactCycleStatus": liquidity["governance"]["formalCycleStatus"],
            "assetForecastStatus": liquidity["governance"]["assetForecastStatus"],
            "gate": {
                "passed": qualified,
                "checks": checks,
                "reasonCodes": [
                    name for name, passed in checks.items() if not passed
                ],
            },
            "caveat": diagnostic["caveat"],
        }

    risk_state = diagnostic.get("riskAppetiteState")
    if cycle_id == "C7" and risk_state:
        checks = {
            "state_model_validated": risk_state["status"]
            == "short_horizon_regime_predictable",
            "1m_validated": risk_state["validation"]["1m"]["qualified"],
            "3m_validated": risk_state["validation"]["3m"]["qualified"],
            "5m_validated": risk_state["pathValidation"]["5m"]["qualified"],
            "6m_not_published": not risk_state["validation"]["6m"]["qualified"],
        }
        qualified = all(checks.values())
        horizons = [
            {
                "label": f"{forecast['horizonMonths']}个月",
                "months": forecast["horizonMonths"],
                "probability": forecast["probabilityRiskOn"],
                "outcome": "风险偏好",
                "accuracy": risk_state["pathValidation"][
                    f"{forecast['horizonMonths']}m"
                ]["accuracy"],
                "qualified": forecast["qualified"],
            }
            for forecast in risk_state["forecastPath"]
            if forecast["qualified"]
        ]
        return {
            "status": "limited" if qualified else "blocked",
            "layer": "risk_state_probability",
            "badgeLabel": "状态可用" if qualified else "状态阻断",
            "label": "1–5个月风险区间状态",
            "asOf": risk_state["current"]["date"],
            "currentLabel": risk_state["current"]["regime"],
            "horizons": horizons,
            "exactCycleStatus": risk_state["governance"]["formalCycleStatus"],
            "assetForecastStatus": risk_state["governance"]["assetForecastStatus"],
            "gate": {
                "passed": qualified,
                "checks": checks,
                "reasonCodes": [
                    name for name, passed in checks.items() if not passed
                ],
            },
            "caveat": diagnostic["caveat"],
        }
    return None


def _blocked_cycle_diagnostics(
    monthly_panel: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
) -> dict[str, Any]:
    annual_panel = pd.read_parquet(
        PROJECT_ROOT / "data" / "indicator_panel_annual_very_long_history_year.parquet"
    ).loc[1700:2024]
    c2 = _diagnostic_payload(
        cycle_id="C2",
        frequency="A",
        panel=annual_panel,
        families={
            "房价与建设": [
                ("UK_BOE_HOUSE_PRICE_INDEX_2015_01_100_EXT_OECD", "log_change", 1.0),
                ("UK_BOE_A1_17_Stockbuilding_contribution", "level", 1.0),
            ],
            "按揭与信用": [
                ("UK_BOE_A1_48_Mortgage_rates", "diff", -1.0),
                ("UK_BOE_A1_58_Secured_credit", "log_change", 1.0),
            ],
            "人口需求": [
                ("MPD_GBR_POP_THOUSANDS_EXT_WB_GROWTH", "level", 1.0),
                ("MPD_USA_POP_THOUSANDS_EXT_WB_GROWTH", "level", 1.0),
            ],
            "宏观产出": [
                ("UK_GDP_COMPOSITE_INDEX_2013_100_EXT_WB", "log_change", 1.0),
                ("MPD_GBR_GDP_MN_2011_INTL_EXT_WB_GROWTH", "level", 1.0),
            ],
        },
        candidate_periods=[16.8, 20.0, 27.0],
        state_span=5,
        slope_lag=1,
        model_rebuild={
            "recommended": "地产—信用双层因子 + 时变周期状态空间",
            "state": "住房动量与按揭信用定义周期核心；总投资脉冲和融资条件只做确认；估值、杠杆和投资水平单独描述结构位置。",
            "validation": "递归样本外、国家留一、前后半样本、红噪声频谱与当前数据桥接同时验证。",
            "why": "固定200个月谐波与慢趋势、C3资本形成混叠；拆层后可保留1至3年因子方向，并阻止总投资水平锁定C2周期长度。",
        },
        blockers=["固定200个月峰值跨国一致性仍不足", "精确幅度与精确拐点尚未稳定", "2021年后使用BIS/世界银行桥接口径"],
        unlock_conditions=["建立可复核的真实vintage递归库", "精确幅度和转折概率持续优于随机游走基准", "中国地产状态完成独立本土数据验证"],
    )
    capital_columns = [
        (f"WB_{country}_GROSS_CAPITAL_FORMATION_PCT_GDP", "level", 1.0)
        for country in ("USA", "GBR", "DEU", "JPN", "CHN")
    ]
    c3 = _diagnostic_payload(
        cycle_id="C3",
        frequency="A",
        panel=annual_panel,
        families={
            "资本形成": capital_columns + [("UK_BOE_A1_16_Real_investment", "log_change", 1.0)],
            "资本服务": [("UK_BOE_A1_29_Capital_Services_whole_economy", "log_change", 1.0)],
            "生产率": [
                ("UK_BOE_A1_30_TFP_growth", "level", 1.0),
                ("UK_BOE_A1_31_Labour_productivity", "log_change", 1.0),
            ],
            "融资条件": [
                ("UK_BOE_A1_49_Corporate_borrowing_rate_from_banks", "diff", -1.0),
                ("UK_BOE_A1_50_Corporate_bond_yields", "diff", -1.0),
            ],
        },
        candidate_periods=[8.9, 10.7, 15.0],
        state_span=3,
        slope_lag=1,
        model_rebuild={
            "recommended": "JST跨国资本面板 + 投资/企业信用方向分类器",
            "state": "资本形成、企业信用、实际增长和融资条件形成国家层状态；8至12年频带仅作为漂移先验。",
            "validation": "递归样本外、国家留一、前后半样本和不同家族删减同时验证。",
            "why": "C3的方向概率比固定100个月相位角稳定，模型应先预测1至3年方向，再估计时变周期中心。",
        },
        blockers=["固定100个月峰在跨国综合因子中漂移到8至12年", "精确幅度跨时期仍不稳定", "利润率与产能利用率长历史仍不足"],
        unlock_conditions=["补齐利润率、产能利用率和设备投资vintage", "精确幅度与转折概率跨时期稳定", "中国资本形成与企业利润完成独立验证"],
    )
    c5 = _diagnostic_payload(
        cycle_id="C5",
        frequency="M",
        panel=monthly_panel.loc[:as_of],
        families={
            "国内政策流动性": [
                ("CN_M_M2_YOY", "level", 1.0),
                ("CN_LPR_1Y_AK_LEVEL", "diff", -1.0),
                ("CN_SHIBOR_ON_AK_LEVEL", "diff", -1.0),
                ("CN_REPO_R007_LEVEL", "diff", -1.0),
            ],
            "信用传导": [
                ("CN_M_M1_YOY", "level", 1.0),
                ("CN_SF_STOCK_YOY", "level", 1.0),
                ("CN_SF_FLOW12_YOY", "level", 1.0),
            ],
            "全球美元流动性": [
                ("US_FEDFUNDS_LEVEL", "diff", -1.0),
                ("US_BROAD_DOLLAR_MOM", "level", -1.0),
                ("US_FED_BALANCE_SHEET_YOY", "level", 1.0),
            ],
        },
        candidate_periods=[12.0, 20.0, 27.0],
        state_span=4,
        slope_lag=3,
        model_rebuild={
            "recommended": "流动性冲击动态因子 + 政策事件状态空间",
            "state": "用信用脉冲、政策利率、资金利率和美元条件刻画方向，不先假设固定 20 个月周期。",
            "validation": "政策事件前后、实时 vintage、不同加速度口径和资产价格领先性。",
            "why": "流动性受政策离散冲击驱动，更适合状态与冲击模型，而非稳定谐波。",
        },
        blockers=["12–27 个月候选分散", "水平与脉冲口径结论不一致", "中国信用脉冲与政策操作 vintage 不完整"],
        unlock_conditions=["补齐社融结构、回购、MLF、逆回购和财政投放", "冲击状态递归识别稳定", "资产价格与信用变量样本外方向一致"],
    )
    c7 = _diagnostic_payload(
        cycle_id="C7",
        frequency="M",
        panel=monthly_panel.loc[:as_of],
        families={
            "市场收益": [
                ("US_FF3_MKT_RF_RET", "level", 1.0),
                ("IDX_CSI500_MOM", "level", 1.0),
                ("IDX_GEM_MOM", "level", 1.0),
            ],
            "风格风险偏好": [
                ("IDX_CSI300_HIGH_BETA_MOM", "level", 1.0),
                ("IDX_CSI_DIV_LOWVOL_MOM", "level", -1.0),
                ("US_FF_MOM_RET", "level", 1.0),
            ],
            "交易活跃度": [
                ("IDX_SZ_COMP_TURNOVER_RATE_LEVEL", "diff", 1.0),
                ("IDX_SH_COMP_TURNOVER_RATE_LEVEL", "diff", 1.0),
            ],
            "外部避险": [("DXY_MOM", "level", -1.0)],
        },
        candidate_periods=[5.6, 6.0, 9.0],
        state_span=3,
        slope_lag=1,
        model_rebuild={
            "recommended": "高频风险偏好动态因子 + Markov 状态切换",
            "state": "收益、风格、换手、融资拥挤、外部避险、波动与信用压力共同决定风险状态，周期长度作为条件统计而非先验约束。",
            "validation": "月度递归状态、近年留出、非价格资产门槛和状态持续期稳定性。",
            "why": "市场交易状态会因波动与拥挤突然切换，固定 6 个月波容易产生虚假规律。",
        },
        blockers=["市场收益与广度触及 9 个月上界", "约 5.6 个月仅在部分风格家族出现", "缺少稳定长历史广度、流量和拥挤指标"],
        unlock_conditions=["补齐市场广度和基金流长历史", "6个月状态概率跨时期稳定", "非价格资产方向样本外优于静态基准"],
    )
    long_panel_path = PROJECT_ROOT / "output" / "c2_c3_long_panel_research.json"
    if long_panel_path.exists():
        long_panel = json.loads(long_panel_path.read_text(encoding="utf-8"))
        for cycle_id, diagnostic in (("C2", c2), ("C3", c3)):
            diagnostic["longPanel"] = long_panel["cycles"][cycle_id]
            diagnostic["longPanelSources"] = long_panel["sources"]
            diagnostic["caveat"] = (
                "JST/BIS/世界银行跨国面板支持1至3年方向概率研究；正式相位、精确幅度、精确拐点和资产归因仍保持阻断。"
            )
    if C5_LIQUIDITY_STATE.exists():
        liquidity_state = json.loads(C5_LIQUIDITY_STATE.read_text(encoding="utf-8"))
        c5["liquidityState"] = liquidity_state
        c5["caveat"] = (
            "国内政策、信用传导和全球美元三层状态的3至12个月方向通过递归样本外验证；固定20个月周期、精确政策拐点和资产收益风险预测继续阻断。"
        )
        c5["blockers"] = [
            "真实政策操作vintage仍不完整",
            "固定20个月频带不稳定",
            "分股票、债券、商品和外汇的收益风险增量验证未通过",
        ]
    if C7_RISK_APPETITE_STATE.exists():
        risk_appetite_state = json.loads(
            C7_RISK_APPETITE_STATE.read_text(encoding="utf-8")
        )
        c7["riskAppetiteState"] = risk_appetite_state
        c7["caveat"] = (
            "风险偏好状态未来1至5个月处于正区间的概率通过递归样本外验证；这不等于状态继续上行。固定6个月周期、6个月路径和非价格资产方向继续阻断。"
        )
        c7["blockers"] = [
            "6个月风险状态概率未通过完整样本门槛",
            "成交、融资与美元非价格信号未通过资产方向验证",
            "市场广度与基金流长历史仍不足",
        ]
    for cycle_id, diagnostic in (("C2", c2), ("C3", c3), ("C5", c5), ("C7", c7)):
        direction_publication = _direction_publication_payload(cycle_id, diagnostic)
        if direction_publication:
            diagnostic["directionPublication"] = direction_publication
    return {"C2": c2, "C3": c3, "C5": c5, "C7": c7}


def _track_payload(
    spec: TrackSpec,
    raw: pd.Series,
    c4_history: pd.Series,
    c4_forecast: list[dict[str, Any]],
    change_history: pd.Series | None = None,
    *,
    as_of: pd.Timestamp,
    forecast_as_of: str,
) -> dict[str, Any]:
    raw = raw.loc[:as_of].astype(float)
    change = _change(raw, spec.transform)
    if change_history is not None:
        change_history = change_history.loc[:as_of].astype(float)
        full_index = raw.index.union(change_history.index).sort_values()
        raw = raw.reindex(full_index)
        change = change.reindex(full_index).combine_first(change_history.reindex(full_index))
    start = change.first_valid_index() or raw.first_valid_index()
    if start is None:
        raise ValueError(f"Track {spec.track_id} has no observations")
    series_end = change.last_valid_index() or raw.last_valid_index()
    if series_end is None:
        raise ValueError(f"Track {spec.track_id} has no ending observation")
    raw = raw.loc[start:series_end]
    change = change.reindex(raw.index)
    standardized = _rolling_z(change)
    components = _cycle_components(standardized)
    contribution_components = _gaussian_fft_cycle_components(standardized)
    comparison_components = _butterworth_cycle_components(standardized)
    cycle_contribution = build_cross_filter_indicator_cycle_contribution(
        standardized,
        contribution_components,
        comparison_components,
        primary_filter="gaussian_fft",
        comparison_filter="butterworth_zero_phase",
    )
    governed = _stack(components, ("C4", "C6"))
    research = _stack(components, ("C2", "C3", "C4", "C5", "C6", "C7"))
    forecast = build_track_forecast(
        track_id=spec.track_id,
        series=governed,
        c4_history=c4_history,
        c4_forecast=c4_forecast,
        forecast_as_of=forecast_as_of,
    )
    raw_start = raw.first_valid_index()
    end = raw.last_valid_index()
    return {
        "id": spec.track_id,
        "label": spec.label,
        "category": spec.category,
        "group": spec.group,
        "unit": spec.unit,
        "frequency": spec.frequency,
        "source": spec.source,
        "sourceCode": spec.source_code,
        "transform": spec.transform,
        "proxyStatus": spec.proxy_status,
        "caveat": spec.caveat,
        "coverage": {
            "start": _json_value(start),
            "end": _json_value(end),
            "observations": int(raw.notna().sum()),
            "rawStart": _json_value(raw_start),
            "changeObservations": int(change.notna().sum()),
        },
        "dates": [timestamp.strftime("%Y-%m") for timestamp in raw.index],
        "raw": _json_array(raw),
        "change": _json_array(change),
        "standardized": _json_array(standardized),
        "governedStack": _json_array(governed),
        "researchStack": _json_array(research),
        "cycleComponents": {
            cycle_id: _json_array(component.reindex(raw.index))
            for cycle_id, component in components.items()
        },
        "cycleContribution": cycle_contribution,
        "forecast": forecast,
        "_realtimeStandardized": standardized,
    }


def _attach_realtime_indicator_confirmations(
    tracks: list[dict[str, Any]],
) -> None:
    pool_inputs: dict[str, dict[str, object]] = {}
    track_metadata: dict[str, dict[str, object]] = {}
    for track in tracks:
        track_id = str(track["id"])
        track_metadata[track_id] = {
            "category": track["category"],
            "group": track["group"],
        }
        standardized = track.get("_realtimeStandardized")
        contribution = track.get("cycleContribution")
        if isinstance(standardized, pd.Series) and isinstance(contribution, dict):
            pool_inputs[track_id] = build_realtime_indicator_peer_pool_input(
                standardized,
                contribution,
            )
    peer_pools = build_peer_shared_error_pools(pool_inputs, track_metadata)
    for track in tracks:
        track_id = str(track["id"])
        standardized = track.pop("_realtimeStandardized", None)
        contribution = track.get("cycleContribution")
        if not isinstance(contribution, dict):
            continue
        if (
            contribution.get("status") == "retrospective_diagnostic"
            and isinstance(standardized, pd.Series)
        ):
            contribution["realtimeConfirmation"] = (
                build_realtime_indicator_confirmation(
                    standardized,
                    contribution,
                    peer_shared_errors=peer_pools.get(track_id),
                )
            )
            paths = contribution.pop("paths")
            contribution["paths"] = {
                "baseline": _json_value(paths["baseline"]),
                "cycleTotal": _json_array(
                    paths["cycleTotal"].reindex(standardized.index)
                ),
                "residual": _json_array(
                    paths["residual"].reindex(standardized.index)
                ),
                "components": {
                    cycle_id: _json_array(series.reindex(standardized.index))
                    for cycle_id, series in paths["components"].items()
                },
            }
        track["cycleContribution"] = _json_structure(contribution)


def _panel_track_spec(
    column: str,
    group: str,
    ordinal: int,
    proxy_audit: dict[str, Any] | None = None,
) -> TrackSpec:
    label = column
    category = "扩展经济指标" if group == "economic" else "扩展市场指标"
    unit = "标准化值"
    transform = "diff"
    if column.endswith("_RET"):
        transform = "percent_value"
        unit = "%月收益"
        match = re.match(r"US_FF(?:17|30|38|48)IND_(.+)_RET$", column)
        if match:
            label = f"美股行业 · {match.group(1)}"
            category = "美股行业"
    elif column.endswith("_TRAIL12"):
        transform = "percent_value"
        unit = "%近12月收益"
    elif column.endswith("_YOY"):
        transform = "percent_value"
        unit = "%同比"
    elif column.endswith("_MOM"):
        transform = "percent_value"
        unit = "%环比"
    elif column.endswith("_LEVEL"):
        transform = "diff" if any(token in column for token in ("IR_", "RATE", "PMI")) else "log_change"
        unit = "原始单位"
    if column.startswith("IDX_"):
        label = f"A股市场 · {column.removesuffix('_LEVEL')}"
        category = "A股指数"
    elif column.startswith("CN_"):
        category = "中国宏观"
    elif column.startswith("US_") and group == "economic":
        category = "美国宏观"
    source = "本地多源研究面板"
    proxy_status = "direct"
    caveat = "列名保留原始数据身份；详细供应商与口径在数据审计页核对。"
    if proxy_audit is not None:
        source = "Tushare Pro直接历史 + 显式OLS尾部代理"
        proxy_status = "proxy"
        caveat = (
            f"真实分项截至 {proxy_audit['directThrough']}；"
            f"{proxy_audit['proxyStart']} 至 {proxy_audit['proxyEnd']} 以"
            f" {proxy_audit['proxyFor']} 线性延伸，重叠期R²={proxy_audit['r2']:.3f}。"
        )
    return TrackSpec(
        track_id=f"panel_{ordinal:03d}",
        label=label,
        category=category,
        group=group,
        unit=unit,
        source=source,
        source_code=column,
        transform=transform,
        proxy_status=proxy_status,
        caveat=caveat,
    )


def _select_panel_tracks(
    panel: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    proxy_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[tuple[TrackSpec, pd.Series]]:
    proxy_lookup = proxy_lookup or {}
    coverage = panel.loc[:as_of].notna().sum()
    market_candidates = [
        column
        for column in panel.columns
        if coverage[column] >= 120
        and (
            str(column).endswith("_RET")
            or (str(column).startswith("IDX_") and str(column).endswith("_LEVEL"))
        )
    ]
    market_candidates = sorted(market_candidates)[:64]
    economic_patterns = (
        "PMI",
        "CPI",
        "PPI",
        "GDP",
        "IP_",
        "EXPORT",
        "IMPORT",
        "M_M",
        "IR_",
        "UNRATE",
        "HIBOR",
        "LPR",
        "TRADE_BALANCE",
    )
    economic_candidates: list[str] = []
    base_seen: set[str] = set()
    for column in sorted(panel.columns):
        text = str(column)
        if coverage[column] < 84 or not any(token in text for token in economic_patterns):
            continue
        base = re.sub(r"_(LEVEL|MOM|YOY)$", "", text)
        if base in base_seen:
            continue
        preferred = text.endswith("_LEVEL") or text.endswith("_YOY")
        if preferred:
            base_seen.add(base)
            economic_candidates.append(text)
        if len(economic_candidates) >= 31:
            break
    selected: list[tuple[TrackSpec, pd.Series]] = []
    ordinal = 1
    for group, candidates in (("market", market_candidates), ("economic", economic_candidates)):
        for column in candidates:
            spec = _panel_track_spec(
                column,
                group,
                ordinal,
                proxy_lookup.get(str(column)),
            )
            selected.append((spec, _monthly(panel[column], as_of=as_of)))
            ordinal += 1
    return selected


def _governance_payload() -> dict[str, Any]:
    config = yaml.safe_load(
        (PROJECT_ROOT / "config" / "seven_cycle" / "cycles.yaml").read_text(
            encoding="utf-8"
        )
    )
    evidence = yaml.safe_load(
        (
            PROJECT_ROOT / "config" / "seven_cycle" / "evidence_baseline.yaml"
        ).read_text(encoding="utf-8")
    )
    evidence_lookup = {row["cycle_id"]: row for row in evidence["cycles"]}
    cycles = []
    for row in config["cycles"]:
        cycles.append(
            {
                "id": row["cycle_id"],
                "name": row["name_zh"],
                "role": row["economic_role"],
                "centerPriorMonths": row["center_prior_months"],
                "periodMode": row["period_mode"],
                "empiricalBandMonths": row["empirical_band_months"],
                "publication": row["publication"],
                "evidence": evidence_lookup[row["cycle_id"]],
            }
        )
    return {"asOf": str(evidence["generated"]), "cycles": cycles}


def _c1_scenario() -> dict[str, Any]:
    payload = build_c1_validation(simulations=500)
    output_path = PROJECT_ROOT / "output" / "c1_long_wave_validation.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _c6_calendar(tracks: list[dict[str, Any]]) -> dict[str, Any]:
    default = [track for track in tracks if track["id"] in DEFAULT_TRACK_IDS]
    rows = []
    for track in default:
        rows.append(
            pd.Series(
                track["standardized"],
                index=pd.to_datetime(track["dates"]),
                dtype=float,
            ).rename(track["id"])
        )
    frame = pd.concat(rows, axis=1)
    monthly_pattern = frame.groupby(frame.index.month).mean().mean(axis=1)
    annual_level = frame.mean(axis=1).groupby(frame.index.year).std(ddof=0)
    return {
        "status": "calendar_only",
        "monthPattern": [
            {"month": int(month), "value": _json_value(value)}
            for month, value in monthly_pattern.items()
        ],
        "annualAmplitude": [
            {"year": int(year), "value": _json_value(value)}
            for year, value in annual_level.items()
        ],
        "method": "默认十轨标准化变化的月份均值与逐年季节振幅",
        "caveat": "C6 频率由日历定义，仅解释月份结构与变化振幅。",
    }


def _asset_forecast(
    assets: list[dict[str, Any]],
    c4_forecast: list[dict[str, Any]],
    *,
    forecast_as_of: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    phase_keys = {
        "recovery": "p_recovery",
        "expansion": "p_expansion",
        "downturn": "p_downturn",
        "contraction": "p_contraction",
    }
    for asset in assets:
        if asset.get("data_identity") not in {
            "direct",
            "direct_with_limited_cycle_bridge",
        } or not asset.get("phase_stats"):
            continue
        path = []
        medians = pd.Series([item["median"] for item in c4_forecast], dtype=float)
        slopes = medians.diff(3).fillna(0.0)
        beta_level = float(asset["beta_level"])
        beta_slope = float(asset["beta_slope3"])
        contributions = beta_level * medians + beta_slope * slopes
        for index, forecast in enumerate(c4_forecast):
            probabilities = {
                phase: float(forecast[probability_key])
                for phase, probability_key in phase_keys.items()
            }
            expected_return = sum(
                probabilities[phase]
                * float(asset["phase_stats"][phase]["ann_return"])
                for phase in phase_keys
            )
            expected_vol = math.sqrt(
                sum(
                    probabilities[phase]
                    * float(asset["phase_stats"][phase]["ann_vol"]) ** 2
                    for phase in phase_keys
                )
            )
            path.append(
                {
                    "date": forecast["date"],
                    "phaseMixAnnReturn": _json_value(expected_return),
                    "phaseMixAnnVol": _json_value(expected_vol),
                    "c4AssociationMonthly": _json_value(contributions.iloc[index]),
                }
            )
        horizon_impacts = {}
        for horizon in (3, 6, 12):
            horizon_impacts[str(horizon)] = _json_value(contributions.iloc[:horizon].sum())
        rows.append(
            {
                "assetId": asset["asset_id"],
                "name": asset["name"],
                "category": asset["category"],
                "confidence": asset["confidence"],
                "oosR2": _json_value(asset["oos_r2"]),
                "horizonAssociationImpact": horizon_impacts,
                "path": path,
                "status": "limited",
                "caveat": f"基于 {forecast_as_of} 预测 vintage 的 C4 受限条件延伸，不是最新正式预测，也不是完整七周期绝对收益预测。",
            }
        )
    return rows


def build(
    *,
    refresh_public: bool = False,
    as_of: date | str | pd.Timestamp | None = None,
) -> dict[str, Path]:
    as_of_timestamp = _normalize_as_of(as_of)
    generated_date = date.today().isoformat()
    if refresh_public:
        _refresh_public_sources()
    panel = pd.read_parquet(PROJECT_ROOT / "data" / "indicator_panel_monthly.parquet")
    panel_refresh = (
        json.loads(CURRENT_PANEL_REFRESH.read_text(encoding="utf-8"))
        if CURRENT_PANEL_REFRESH.exists()
        else None
    )
    proxy_lookup = {
        row["column"]: row for row in (panel_refresh or {}).get("proxyColumns", [])
    }
    phase_display = json.loads(
        (PROJECT_ROOT / "output" / "c4_c5_phase_display_prototype_2026-07-19.json").read_text()
    )
    forecast_source = (
        C4_FORECAST_REPRODUCIBLE
        if C4_FORECAST_REPRODUCIBLE.exists()
        else C4_FORECAST_FALLBACK
    )
    forecast_data = json.loads(forecast_source.read_text(encoding="utf-8"))
    realtime_source = (
        C4_REALTIME_BRIDGE if C4_REALTIME_BRIDGE.exists() else C4_REALTIME_FALLBACK
    )
    realtime_data = json.loads(realtime_source.read_text(encoding="utf-8"))
    forecast_as_of = str(forecast_data["meta"]["data_as_of"])
    forecast_stale_months = _month_gap(forecast_as_of, as_of_timestamp)
    forecast_data["meta"] = {
        **forecast_data["meta"],
        "build_as_of": as_of_timestamp.strftime("%Y-%m"),
        "stale_months_at_build": forecast_stale_months,
    }
    asset_source = (
        C4_ASSET_STATISTICS_CURRENT
        if C4_ASSET_STATISTICS_CURRENT.exists()
        else PROJECT_ROOT / "output" / "c4_asset_statistics_prototype_2026-07-19.json"
    )
    asset_data = json.loads(asset_source.read_text(encoding="utf-8"))
    asset_returns_refresh = (
        json.loads(ASSET_RETURNS_REFRESH.read_text(encoding="utf-8"))
        if ASSET_RETURNS_REFRESH.exists()
        else None
    )
    asset_cycle_forecast = (
        json.loads(ASSET_CYCLE_FORECAST.read_text(encoding="utf-8"))
        if ASSET_CYCLE_FORECAST.exists()
        else None
    )
    attribution_stability_counts = (
        asset_cycle_forecast.get("meta", {})
        .get("attributionStability", {})
        .get("statusCounts", {})
        if asset_cycle_forecast
        else {}
    )
    state_asset_association = (
        json.loads(C5_C7_ASSET_ASSOCIATION.read_text(encoding="utf-8"))
        if C5_C7_ASSET_ASSOCIATION.exists()
        else {"cycles": {}}
    )
    historical_mapping_path = PROJECT_ROOT / "output" / "c2_c3_historical_mapping.json"
    historical_mapping = (
        json.loads(historical_mapping_path.read_text(encoding="utf-8"))
        if historical_mapping_path.exists()
        else {"meta": {"phaseLabels": {}}, "cycles": {}}
    )
    c2_regime = (
        json.loads(C2_REGIME_REFACTOR.read_text(encoding="utf-8"))
        if C2_REGIME_REFACTOR.exists()
        else None
    )
    c3_regime = (
        json.loads(C3_REGIME_REFACTOR.read_text(encoding="utf-8"))
        if C3_REGIME_REFACTOR.exists()
        else None
    )
    c4_history = pd.Series(
        [row["rt_level"] for row in realtime_data["timeline"]],
        index=pd.to_datetime([row["date"] for row in realtime_data["timeline"]])
        .to_period("M")
        .to_timestamp("M"),
    )
    default_specs = _default_track_specs(panel)
    default_series = _default_series(panel, as_of=as_of_timestamp)
    legacy_changes = pd.read_parquet(PROJECT_ROOT / "data" / "cycle_dataset_mom.parquet")
    default_change_history = {
        "sp500": legacy_changes["Stooq:^spx:S&P 500"] * 100.0,
        "nasdaq": legacy_changes["Stooq:^ndx:NASDAQ 100"] * 100.0,
        "dxy": legacy_changes["FRED:DTWEXBGS:Dollar Index (DTWEXBGS)"] * 100.0,
        "wti": legacy_changes["FRED:DCOILWTICO:WTI Oil (Daily)"] * 100.0,
    }
    tracks = [
        _track_payload(
            default_specs[track_id],
            default_series[track_id],
            c4_history,
            forecast_data["forecast"],
            default_change_history.get(track_id),
            as_of=as_of_timestamp,
            forecast_as_of=forecast_as_of,
        )
        for track_id in CORE_TRACK_IDS
    ]
    for spec, series in _select_panel_tracks(
        panel,
        as_of=as_of_timestamp,
        proxy_lookup=proxy_lookup,
    ):
        tracks.append(
            _track_payload(
                spec,
                series,
                c4_history,
                forecast_data["forecast"],
                as_of=as_of_timestamp,
                forecast_as_of=forecast_as_of,
            )
        )
    tracks = tracks[:104]
    cross_filter_gain_calibration = apply_cross_filter_gain_calibration(tracks)
    _attach_realtime_indicator_confirmations(tracks)
    market_as_of = max(track["coverage"]["end"] for track in tracks)
    panel_as_of = min(
        as_of_timestamp,
        pd.Timestamp(panel.dropna(how="all").index.max()).to_period("M").to_timestamp("M"),
    ).strftime("%Y-%m")
    group_counts = {
        group: sum(track["group"] == group for track in tracks)
        for group in ("market", "economic")
    }
    forecast_track_counts = {
        status: sum(track["forecast"]["status"] == status for track in tracks)
        for status in ("limited", "blocked", "unavailable")
    }
    stale_track_counts = {
        "over12Months": sum(
            _month_gap(track["coverage"]["end"], as_of_timestamp) > 12
            for track in tracks
        ),
        "over24Months": sum(
            _month_gap(track["coverage"]["end"], as_of_timestamp) > 24
            for track in tracks
        ),
    }
    indicator_contribution_study = summarize_indicator_cycle_contributions(tracks)
    indicator_contribution_study["crossFilterGainCalibration"] = (
        cross_filter_gain_calibration
    )
    indicator_contribution_study["longHistory"] = _annual_indicator_contribution_study()
    indicator_contribution_study = _json_structure(indicator_contribution_study)
    market_payload = {
        "meta": {
            "generated": generated_date,
            "asOf": market_as_of,
            "trackCount": len(tracks),
            "groupCounts": group_counts,
            "defaultTrackIds": CYCLE_IDENTIFICATION_TRACK_IDS,
            "trackPresets": [
                {
                    "id": "cycle",
                    "label": "周期识别轨道",
                    "description": "按增长、通胀、利率信用、美元、股票、商品的传导顺序观察周期。",
                    "trackIds": CYCLE_IDENTIFICATION_TRACK_IDS,
                },
            ],
            "surfaceDefinition": {
                "x": "time",
                "y": "cycle_stacked_standardized_change",
                "z": "track",
            },
            "governedCycles": ["C4", "C6"],
            "researchOnlyCycles": ["C2", "C3", "C5", "C7"],
            "excludedFromMonthlyStack": ["C1"],
            "forecastStatus": "validated_track_level_direct_ridge",
            "forecastVintage": forecast_as_of,
            "forecastStaleMonths": forecast_stale_months,
            "forecastTrackCounts": forecast_track_counts,
            "staleTrackCounts": stale_track_counts,
            "surfaceVintage": "latest_historical_retrospective_endpoint",
        },
        "indicatorContributionStudy": indicator_contribution_study,
        "tracks": tracks,
    }
    governance = _governance_payload()
    diagnostics = _blocked_cycle_diagnostics(panel, as_of=as_of_timestamp)
    for cycle_id in ("C2", "C3"):
        if cycle_id == "C2" and c2_regime:
            continue
        if cycle_id in historical_mapping["cycles"]:
            phase_candidate = {
                key: value
                for key, value in historical_mapping["cycles"][cycle_id].items()
                if key != "assetMapping"
            }
            diagnostics[cycle_id]["phaseCandidate"] = phase_candidate
    if c2_regime:
        diagnostics["C2"]["regimeRefactor"] = c2_regime
        diagnostics["C2"]["modelRebuild"] = {
            "recommended": "住房—按揭活动核心直接状态模型",
            "state": "住房动量与按揭信用定义活动核心；水平和1/2/3年动量共识形成四相位，连续两年确认后才转相。",
            "validation": "跨国递归方向、国家留一、银行危机独立校准、四国BIS季度错位、七周期联合资产样本外验证，以及只统计负收益的资产下行风险审计。",
            "why": "不再用固定200个月谐波定义C2，避免趋势、C3投资和短期反弹被误当作地产周期转相。",
        }
        diagnostics["C2"]["blockers"] = [
            "独立银行危机验证只能覆盖约三成系统性危机",
            "全球C2和全球共同项加本国偏离项对多数资产的未来收益、风险样本外R²仍为负",
            "20年月频七周期联合样本不足以稳健验证36个月非重叠目标",
            "股票、国债和短票分开定义12个资产—期限目标后，C2相对资产自身基线仍为0/12通道通过",
            "高杠杆后融资转松、地产下行叠加衰退、住房复苏叠加信用扩张三种预注册场景合计0/36条件通道通过",
            "旧3年国债通道把正负收益都计入风险；改为只统计负收益后失效，资产下行风险映射继续阻断",
        ]
        diagnostics["C2"]["unlockConditions"] = [
            "延长中国可复核住房—信用季度历史，并补充日本资产轨道",
            "直接相位在多数资产、收益与风险期限上取得正的绝对样本外R²",
            "国家或区域C2先通过绝对门槛后，再按预注册顺序测试估值、实际利率和信用交互",
            "停止扩充C2单周期资产模型；只在七周期联合框架中保留少量预注册条件交互，并要求联合模型整体样本外通过",
        ]
        diagnostics["C2"]["caveat"] = (
            "C2当前可发布住房—按揭活动核心的收缩状态与1至3年因子方向概率；"
            "现代结构压力和融资确认状态可观察，但旧3年国债风险通道经下行风险口径审计后撤销；"
            "精确200个月周期、精确拐点、当前资产概率、配置建议和因果归因继续阻断。"
        )
    if c3_regime:
        diagnostics["C3"]["regimeRefactor"] = c3_regime
        diagnostics["C3"]["modelRebuild"] = {
            "recommended": "投资脉冲—企业信用双核心动态状态模型",
            "state": "固定投资脉冲与企业信用脉冲定义C3；GDP与实际融资条件只作确认，投资占比只描述结构位置。",
            "validation": "固定共同目标下比较四种架构，并执行递归年份样本外、前后时期、国家留一、参数平台和股票/国债收益风险增量验证。",
            "why": "旧C3把权益收益、投资水平和确认变量等权并入因子，高准确率主要来自因子惯性，无法证明资本周期或资产揭示效应。",
        }
        diagnostics["C3"]["blockers"] = [
            "四种架构均未在1/2/3年同时稳定战胜双核心自身惯性",
            f"股票和国债收益风险仅{c3_regime['assetValidation']['passedTargets']}/{c3_regime['assetValidation']['targetCount']}通道通过",
            "企业利润率和产能利用率缺少可复核长历史",
            "黄金、原油和铜的直接长历史不足以覆盖多个C3周期",
        ]
        diagnostics["C3"]["unlockConditions"] = [
            "补齐企业利润率、产能利用率和设备投资的跨国历史与实时桥接",
            "双核心相对自身惯性在1/2/3年、前后时期和国家留一中同时稳定改善",
            "股票、国债和直接商品多数收益风险通道取得正的独立样本外增量",
        ]
        diagnostics["C3"]["caveat"] = (
            "C3当前可研究发布投资—信用双核心的动态宽状态与受限方向概率；"
            "100个月只作弱先验，股票和国债仅1/8通道通过，资产概率、配置权重、精确周期和精确拐点继续阻断。"
        )
    c2_c3_as_of = diagnostics["C2"]["longPanel"]["partialNowcast"]["asOfPeriod"]
    cycle_payload = {
        "meta": {
            "generated": generated_date,
            "phaseDefinition": "0°谷底，90°上行过零，180°峰值，270°下行过零",
            "fixedSineWaves": False,
        },
        "governance": governance,
        "C1": _c1_scenario(),
        "C4": phase_display["C4"],
        "C4Realtime": realtime_data,
        "C4Forecast": forecast_data,
        "C6": _c6_calendar(tracks),
        "diagnostics": diagnostics,
        "indicatorContributionStudy": indicator_contribution_study,
    }
    research_mappings = historical_mapping.get("cycles", {})
    if c2_regime:
        research_mappings["C2"] = {
            "cycleId": "C2",
            "status": "direct_regime_mapping_candidate",
            "formalStatus": "blocked",
            "assetMapping": c2_regime["historicalAssetMapping"],
            "geographicState": c2_regime["geographicState"],
            "regimeRefactor": c2_regime,
            "caveat": c2_regime["historicalAssetMapping"].get(
                "method",
                {},
            ).get("validation", "仅历史统计，不是资产预测。"),
        }
    if c3_regime and "C3" in research_mappings:
        legacy_asset_mapping = research_mappings["C3"]["assetMapping"]
        legacy_asset_mapping.pop("currentProbabilityWeightedScenario", None)
        legacy_asset_mapping.update(
            {
                "status": "legacy_mapping_rebuild_required",
                "assetForecastStatus": "blocked",
                "title": "C3 旧口径历史映射已暂停",
                "caveat": (
                    "该表基于重构前的多家族C3状态，与当前投资脉冲—企业信用双核心不再同口径；"
                    "数据仅保留审计，不展示为当前C3资产结论。"
                ),
            }
        )
        research_mappings["C3"]["regimeRefactor"] = c3_regime
        research_mappings["C3"]["assetValidation"] = c3_regime[
            "assetValidation"
        ]
    for cycle_id in ("C2", "C3"):
        long_panel = diagnostics.get(cycle_id, {}).get("longPanel")
        if cycle_id not in research_mappings or not long_panel:
            continue
        direction_model = (
            c3_regime
            if cycle_id == "C3" and c3_regime
            else long_panel
        )
        research_mappings[cycle_id]["currentDirection"] = {
            "status": "cycle_direction_only",
            "currentForecasts": direction_model["currentForecasts"],
            "partialNowcast": direction_model.get("partialNowcast"),
            "currentPhaseCandidate": (
                {
                    "asOfPeriod": c2_regime["meta"]["asOfPeriod"],
                    "current": c2_regime["state"]["current"],
                    "governedBroadState": {
                        "status": "limited_broad_state",
                        "label": "收缩期",
                    },
                    "exactPhaseStatus": "limited",
                    "transitionEvidence": c2_regime["state"]["transitionEvidence"],
                    "familyStates": c2_regime["state"]["familyStates"],
                }
                if cycle_id == "C2" and c2_regime
                else {
                    "status": "limited_current_phase_candidate",
                    "asOfPeriod": c3_regime["meta"]["asOfPeriod"],
                    "current": c3_regime["state"]["current"],
                    "governedBroadState": {
                        "status": "limited_broad_state",
                        "label": {
                            "recovery": "复苏",
                            "expansion": "扩张",
                            "slowdown": "放缓",
                            "contraction": "收缩",
                        }.get(
                            c3_regime["state"]["current"]["phase"],
                            c3_regime["state"]["current"]["phase"],
                        ),
                    },
                    "exactPhaseStatus": "limited",
                    "parameterRobustness": c3_regime["state"][
                        "parameterRobustness"
                    ],
                }
                if cycle_id == "C3" and c3_regime
                else research_mappings[cycle_id].get("currentPhaseCandidate")
            ),
            "assetForecastStatus": "blocked",
            "regimeState": (
                c2_regime["state"]["current"]
                if cycle_id == "C2" and c2_regime
                else c3_regime["state"]["current"]
                if cycle_id == "C3" and c3_regime
                else None
            ),
            "caveat": "周期方向概率可用于研究当前宏观状态，但尚不能转换为单个资产的绝对收益、波动或权重预测。",
        }
    if asset_cycle_forecast:
        asset_cycle_forecast["meta"] = {
            **asset_cycle_forecast["meta"],
            "layer": "joint_state_forecast",
            "includedCycles": ["C4", "C5", "C7"],
            "separateFromSingleCycleMapping": True,
        }
    asset_base_meta = asset_data.get("meta", {})
    forecast_meta = asset_cycle_forecast.get("meta", {}) if asset_cycle_forecast else {}
    asset_payload = {
        **asset_data,
        "meta": {
            **asset_base_meta,
            "generated": generated_date,
            "historicalStatisticsGenerated": asset_base_meta.get("generated"),
            "historicalStatisticsAsOf": max(
                (
                    row.get("end")
                    for row in asset_data.get("assets", [])
                    if row.get("end")
                ),
                default=None,
            ),
            "forecastGenerated": forecast_meta.get("generated"),
            "forecastAsOf": forecast_meta.get("asOf"),
            "forecastAssetDataThrough": forecast_meta.get("assetDataThrough"),
        },
        "publication": {
            cycle["id"]: cycle["publication"]["asset_statistics"]
            for cycle in governance["cycles"]
        },
        "researchPhaseLabels": historical_mapping["meta"].get("phaseLabels", {}),
        "researchMappings": research_mappings,
        "stateMappings": state_asset_association["cycles"],
        "stateDiagnostics": {
            "C5": diagnostics.get("C5", {}).get("liquidityState"),
            "C7": diagnostics.get("C7", {}).get("riskAppetiteState"),
        },
        "currentCycleForecast": asset_cycle_forecast,
    }
    forecast_payload = {
        "meta": forecast_data["meta"],
        "modelSummary": forecast_data["model_summary"],
        "qualifiedModels": forecast_data["qualified_models"],
        "history": forecast_data["history"],
        "forecast": forecast_data["forecast"],
        "phaseWindows": forecast_data["phase_windows"],
        "eligibility": forecast_data["eligibility"],
        "assetConditionalForecasts": _asset_forecast(
            asset_data["assets"],
            forecast_data["forecast"],
            forecast_as_of=forecast_as_of,
        ),
    }
    audit_payload = {
        "meta": {"generated": generated_date, "asOf": as_of_timestamp.strftime("%Y-%m")},
        "governance": governance,
        "sources": [
            {
                "entity": "市场曲面默认轨道",
                "source": "FRED / ISM proxy / Yahoo Finance / explicit panel proxies",
                "vintage": "latest_historical",
                "asOf": market_as_of,
                "status": "mixed_direct_and_explicit_proxy",
            },
            {
                "entity": "美国 PMI（新订单代理）",
                "source": "FRED: AMTMNO 制造商新订单",
                "vintage": "latest_historical",
                "asOf": next(
                    track["coverage"]["end"]
                    for track in tracks
                    if track["id"] == "us_pmi"
                ),
                "status": "explicit_leading_proxy_not_pmi_level",
            },
            {
                "entity": "周期—指标频带贡献研究",
                "source": "104条市场与经济轨道的标准化变化及C2-C7滤波分量",
                "vintage": "latest_historical_retrospective_endpoint",
                "asOf": market_as_of,
                "status": "ridge_reconstruction_with_explicit_residual_not_causal",
            },
            {
                "entity": "C4 历史相位",
                "source": "output/c4_c5_phase_display_prototype_2026-07-19.json",
                "vintage": "latest_historical",
                "asOf": "2025-12",
                "status": "formal_historical",
            },
            {
                "entity": "C4 单边状态桥接",
                "source": str(realtime_source.relative_to(PROJECT_ROOT)),
                "vintage": "latest_restated_indicator_bridge",
                "asOf": realtime_data["latest"]["date"],
                "status": "validated_bridge_limited_not_true_vintage",
            },
            {
                "entity": "C4 预测",
                "source": str(forecast_source.relative_to(PROJECT_ROOT)),
                "vintage": "latest_historical",
                "asOf": forecast_as_of,
                "status": f"limited_stale_input_{forecast_stale_months}m",
            },
            {
                "entity": "市场轨道条件预测",
                "source": "轨道自身滞后/斜率 + C4条件路径 + 月份季节项",
                "vintage": "chronological_holdout_track_level_ridge",
                "asOf": market_as_of,
                "status": f"{forecast_track_counts['limited']}_tracks_limited_{forecast_track_counts['blocked']}_blocked",
            },
            {
                "entity": "C4 资产统计",
                "source": str(asset_source.relative_to(PROJECT_ROOT)),
                "vintage": "latest_historical_plus_limited_realtime_bridge",
                "asOf": max(
                    (row.get("end") for row in asset_data["assets"] if row.get("end")),
                    default="unavailable",
                ),
                "status": "formal_historical_with_limited_realtime_bridge",
            },
            {
                "entity": "现实资产收益增量刷新",
                "source": "Tushare Pro + Akshare + Yahoo adjusted close + Ken French Data Library + 本地指标面板",
                "vintage": "mixed_current_and_source_reporting_lag",
                "asOf": asset_cycle_forecast["meta"]["asOf"] if asset_cycle_forecast else "unavailable",
                "status": (
                    f"{asset_cycle_forecast['summary']['refreshedAssets']}_current_"
                    f"{asset_cycle_forecast['summary']['sourceLagAssets']}_source_lag_"
                    f"{asset_cycle_forecast['summary']['staleAssets']}_stale"
                    if asset_cycle_forecast
                    else "stale"
                ),
            },
            {
                "entity": "逐资产周期状态条件预测",
                "source": "C4/C5上月状态 + C7与资产当月状态的异步发布时钟",
                "vintage": "latest_restated_state_recursive_oos",
                "asOf": asset_cycle_forecast["meta"]["asOf"] if asset_cycle_forecast else "unavailable",
                "status": "limited_asset_level_only" if asset_cycle_forecast else "blocked",
            },
            {
                "entity": "C5/C7 资产历史统计关联",
                "source": str(C5_C7_ASSET_ASSOCIATION.relative_to(PROJECT_ROOT)),
                "vintage": "latest_restated_state_not_true_vintage",
                "asOf": panel_as_of,
                "status": "research_association_only_not_causal_not_forecast",
            },
            {
                "entity": "C5/C7 当前状态增量刷新",
                "source": panel_refresh["source"] if panel_refresh else "月频研究面板",
                "vintage": "incremental_latest_completed_month" if panel_refresh else "latest_historical",
                "asOf": panel_as_of,
                "status": f"{panel_refresh['updatedColumnCount']}_columns_refreshed" if panel_refresh else "research_diagnostic_not_published",
            },
            {
                "entity": "C2/C3 长历史方向验证",
                "source": "JST R6 + BIS住宅价格/总信用 + OECD短端利率/房价租金比 + 世界银行固定资本形成/CPI",
                "vintage": "historical_panel_plus_current_bridge",
                "asOf": c2_c3_as_of,
                "status": "direction_probability_validated_not_formal_phase",
            },
            {
                "entity": "C2/C3 历史相位与资产映射候选",
                "source": "JST 18国资产收益 + Ken French 48行业/25规模价值组合",
                "vintage": "causal_historical_reconstruction",
                "asOf": "2020-12-31",
                "status": "research_phase_and_mapping_candidate",
            },
            {
                "entity": "C2 直接状态与七周期边际资产验证",
                "source": "JST住房—按揭核心 + BIS/OECD/世界银行现代结构压力桥接 + 98条月频资产暴露注册表",
                "vintage": "causal_historical_plus_current_bridge",
                "asOf": c2_regime["meta"]["asOfPeriod"] if c2_regime else "unavailable",
                "status": "limited_regime_asset_forecast_blocked",
            },
            {
                "entity": "C3 投资—信用双核心重构",
                "source": "JST投资/企业信用 + BIS企业信用 + World Bank投资/GDP/融资 + OECD季度实际固定资本形成",
                "vintage": "causal_historical_plus_current_bridge",
                "asOf": c3_regime["meta"]["asOfPeriod"] if c3_regime else "unavailable",
                "status": "limited_dynamic_state_asset_forecast_blocked",
            },
        ],
        "c2C3Sources": diagnostics.get("C2", {}).get("longPanelSources", []),
        "proxyColumns": (panel_refresh or {}).get("proxyColumns", []),
        "calibrations": [
            {"subject": "C1", "version": "v6", "status": "scenario_only", "decision": "全球实体核心保留七家族；资本形成和全球连接桥接至当前，现代技术扩散因仅9年重叠且相关系数约0.05被拒绝续接。端点动量由改善修正为平稳，35至70年频带仍为0/7通过红噪声检验，因此不发布精确相位、预测和独立配置权重。"},
            {"subject": "C2", "version": "v15", "status": "limited", "decision": "完成C2条件传播终局验证。预注册高杠杆后融资转松、地产下行叠加经济衰退、住房复苏叠加信用扩张三种场景，对股票、国债和短票12个资产—期限目标形成36个通道；全样本、条件期、参数平台、前后时期和国家留一合计0/36通过，其中复苏场景12项覆盖不足。停止继续扩充C2单周期资产预测模型，C2仅保留宏观状态、结构/融资确认，以及七周期联合模型中的少量预注册条件交互。"},
            {"subject": "C3", "version": "v5", "status": "limited", "decision": "完成投资脉冲—企业信用双核心重构。100个月仅作弱先验，当前动态状态为复苏、候选周期约10.1年；四架构相对因子惯性均未全期限通过，股票和国债收益风险仅1/8通道通过，资产预测和配置继续阻断。"},
            {"subject": "C4", "version": "v4", "status": "formal", "decision": "历史相位与资产统计可发布。"},
            {"subject": "C4 实时桥接", "version": "v2", "status": "limited", "decision": f"PMI/PPI 指标桥接通过历史截点验证，单边状态延伸至 {realtime_data['latest']['date']}；因不是真实发布 vintage，继续受限。"},
            {"subject": "C4 预测", "version": "v2", "status": "limited", "decision": f"已建立可重复 Ridge 预测脚本并重跑门槛；当前仍使用 {forecast_as_of} 状态输入，滞后 {forecast_stale_months} 个月。"},
            {"subject": "C6", "version": "v2", "status": "calendar_only", "decision": "仅发布月份结构和季节振幅。"},
            {"subject": "C5 流动性状态", "version": "v5", "status": "limited", "decision": f"国内政策流动性、信用传导和全球美元流动性三层刷新至 {panel_as_of}；3至12个月非线性状态路径通过，NFCI仅作确认，资产收益风险增量仍阻断。"},
            {"subject": "C7 风险偏好状态", "version": "v7", "status": "limited", "decision": f"市场、换手、融资及压力信号刷新至 {panel_as_of}；1至5个月未来状态处于风险偏好区间的概率通过。资产验证扩展为五类资产×1/3/6个月×收益/风险30个通道，只允许滞后成交、融资和美元避险信号提供增量，未通过前继续阻断。"},
            {"subject": "C5/C7 资产统计关联", "version": "v1", "status": "research_only", "decision": "开放逐资产历史状态分区、HAC关联系数和样本外R²；不升级为因果归因或资产方向预测。"},
            {"subject": "资产收益当前层", "version": "v2", "status": "limited", "decision": f"{asset_cycle_forecast['summary']['refreshedAssets'] if asset_cycle_forecast else 0}条资产刷新至当前截点，{asset_cycle_forecast['summary']['sourceLagAssets'] if asset_cycle_forecast else 0}条处于官方源端正常滞后，{asset_cycle_forecast['summary']['staleAssets'] if asset_cycle_forecast else 0}条真正过期；FF17使用Ken French官方完整月频历史，当前仅发布至{asset_returns_refresh.get('sourceDataEnd', '源端最新月') if asset_returns_refresh else '源端最新月'}，不静默外推。"},
            {"subject": "逐资产周期状态预测", "version": "v8", "status": "limited", "decision": f"保持1/3/6个月原发布门槛不变；对最终通过资产使用8组反事实和Shapley值拆解C4/C5/C7贡献。24个非重叠历史截点复核结果：稳定{attribution_stability_counts.get('stable', 0)}项、混合{attribution_stability_counts.get('mixed', 0)}项、周期增量较小{attribution_stability_counts.get('low_impact', 0)}项、不稳定{attribution_stability_counts.get('unstable', 0)}项。该结果是模型敏感度，不是因果归因。"},
        ],
    }
    outputs = {
        "market": WEB_DATA_DIR / "market-surface.json",
        "cycles": WEB_DATA_DIR / "cycle-research.json",
        "assets": WEB_DATA_DIR / "asset-statistics.json",
        "forecast": WEB_DATA_DIR / "forecast-extension.json",
        "audit": WEB_DATA_DIR / "data-calibration.json",
        "spec": PROJECT_ROOT / "web" / "public" / "docs" / "2026-07-19-seven-cycle-research-system-redesign.md",
    }
    _write_json(outputs["market"], market_payload)
    _write_json(outputs["cycles"], cycle_payload)
    _write_json(outputs["assets"], asset_payload)
    _write_json(outputs["forecast"], forecast_payload)
    _write_json(outputs["audit"], audit_payload)
    outputs["spec"].parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        PROJECT_ROOT / "docs" / "superpowers" / "specs" / "2026-07-19-seven-cycle-research-system-redesign.md",
        outputs["spec"],
    )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-public", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    outputs = build(refresh_public=args.refresh_public, as_of=args.as_of)
    print(
        json.dumps(
            {name: str(path.relative_to(PROJECT_ROOT)) for name, path in outputs.items()},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
