#!/usr/bin/env python3
"""Validate C1 as a limited long-wave structural indicator."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from scipy.signal import butter, periodogram, sosfiltfilt
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    from scripts.c1_global_core import build_global_core_panel
    from scripts.research_c1_global_proxy_analysis import build_analysis as build_proxy_analysis
except ModuleNotFoundError:
    from c1_global_core import build_global_core_panel
    from research_c1_global_proxy_analysis import build_analysis as build_proxy_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_annual_very_long_history_year.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c1_long_wave_validation.json"
JST_PATH = PROJECT_ROOT / "data" / "raw" / "jst" / "JSTdatasetR6.xlsx"
BCL_PATH = PROJECT_ROOT / "data" / "raw" / "bcl" / "BCLDatabase_online_v2.7.xlsx"
CHAT_PATH = PROJECT_ROOT / "data" / "raw" / "chat" / "FinalCHAT_72909.csv"
ENERGY_PATH = PROJECT_ROOT / "data" / "raw" / "owid" / "global-primary-energy-by-source.csv"
MODERN_TECHNOLOGY_PATH = PROJECT_ROOT / "data" / "raw" / "worldbank" / "c1_technology_diffusion.csv"
START_YEAR = 1600
END_YEAR = 2024
PERIOD_BAND = (35.0, 70.0)


def _finite(value: float | int | None, digits: int = 4) -> float | int | None:
    if value is None or not math.isfinite(float(value)):
        return None
    if isinstance(value, int):
        return value
    return round(float(value), digits)


def _robust_z(series: pd.Series) -> pd.Series:
    median = series.median()
    scale = (series - median).abs().median() * 1.4826
    if not scale or pd.isna(scale):
        return pd.Series(np.nan, index=series.index)
    return ((series - median) / scale).clip(-5.0, 5.0)


def build_family_panel(
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, list[dict[str, Any]], pd.Series]:
    required_sources = (BCL_PATH, JST_PATH, CHAT_PATH, ENERGY_PATH, MODERN_TECHNOLOGY_PATH)
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in required_sources if not path.exists()]
    if missing:
        raise RuntimeError(
            "C1 原始数据缺失："
            + "、".join(missing)
            + "。请先运行 uv run python scripts/refresh_c1_global_sources.py。"
        )
    return build_global_core_panel(
        panel,
        bcl_path=BCL_PATH,
        jst_path=JST_PATH,
        chat_path=CHAT_PATH,
        modern_technology_path=MODERN_TECHNOLOGY_PATH,
        energy_path=ENERGY_PATH,
        start_year=START_YEAR,
        end_year=END_YEAR,
    )


def _weighted_composite(
    family_panel: pd.DataFrame,
    weights: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    available_weight = family_panel.notna().mul(weights, axis=1).sum(axis=1)
    composite = family_panel.mul(weights, axis=1).sum(axis=1, min_count=1) / available_weight.replace(0.0, np.nan)
    return composite, available_weight


def _linear_detrend(values: np.ndarray) -> np.ndarray:
    x = np.arange(len(values), dtype=float)
    valid = np.isfinite(values)
    if valid.sum() < 3:
        return np.full_like(values, np.nan)
    fitted = np.polyval(np.polyfit(x[valid], values[valid], 1), x)
    return values - fitted


def _filled(series: pd.Series) -> np.ndarray:
    return series.interpolate(limit_direction="both").to_numpy(dtype=float)


def _standardize_wave(values: np.ndarray) -> np.ndarray:
    scale = np.nanstd(values)
    return values / scale if scale > 1e-9 else np.zeros_like(values)


def _filter_wave(series: pd.Series, method: str) -> np.ndarray:
    values = _linear_detrend(_filled(series))
    low_period, high_period = PERIOD_BAND
    if method == "gaussian":
        short = gaussian_filter1d(values, low_period / (2.0 * np.pi), mode="nearest")
        long = gaussian_filter1d(values, high_period / (2.0 * np.pi), mode="nearest")
        wave = short - long
    elif method == "butterworth":
        frequencies = (1.0 / high_period, 1.0 / low_period)
        sos = butter(3, frequencies, btype="bandpass", fs=1.0, output="sos")
        wave = sosfiltfilt(sos, values)
    elif method == "fft":
        spectrum = np.fft.rfft(values)
        frequencies = np.fft.rfftfreq(len(values), d=1.0)
        keep = (frequencies >= 1.0 / high_period) & (frequencies <= 1.0 / low_period)
        wave = np.fft.irfft(spectrum * keep, n=len(values))
    else:
        raise ValueError(f"unknown filter method: {method}")
    return _standardize_wave(wave)


def _ensemble_wave(series: pd.Series) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    methods = {name: _filter_wave(series, name) for name in ("gaussian", "butterworth", "fft")}
    return np.nanmedian(np.vstack(list(methods.values())), axis=0), methods


def _band_power_metrics(series: pd.Series, simulations: int, seed: int) -> dict[str, Any]:
    values = _linear_detrend(_filled(series))
    frequencies, power = periodogram(values, fs=1.0, detrend=False)
    valid = (frequencies >= 1.0 / 100.0) & (frequencies <= 1.0 / 20.0)
    band = (frequencies >= 1.0 / PERIOD_BAND[1]) & (frequencies <= 1.0 / PERIOD_BAND[0])
    ratio = float(power[band].sum() / power[valid].sum()) if power[valid].sum() else 0.0
    band_frequencies = frequencies[band]
    band_power = power[band]
    dominant_period = float(1.0 / band_frequencies[np.argmax(band_power)])
    centered = values - np.mean(values)
    phi = float(np.corrcoef(centered[:-1], centered[1:])[0, 1])
    phi = float(np.clip(phi if math.isfinite(phi) else 0.0, -0.95, 0.95))
    innovation_scale = float(np.std(centered[1:] - phi * centered[:-1]))
    rng = np.random.default_rng(seed)
    exceed = 0
    for _ in range(simulations):
        noise = rng.normal(0.0, innovation_scale or 1.0, len(values))
        simulated = np.empty(len(values), dtype=float)
        simulated[0] = noise[0] / math.sqrt(max(1e-6, 1.0 - phi**2))
        for index in range(1, len(values)):
            simulated[index] = phi * simulated[index - 1] + noise[index]
        sim_frequency, sim_power = periodogram(simulated, fs=1.0, detrend="linear")
        sim_valid = (sim_frequency >= 1.0 / 100.0) & (sim_frequency <= 1.0 / 20.0)
        sim_band = (sim_frequency >= 1.0 / PERIOD_BAND[1]) & (sim_frequency <= 1.0 / PERIOD_BAND[0])
        sim_ratio = float(sim_power[sim_band].sum() / sim_power[sim_valid].sum()) if sim_power[sim_valid].sum() else 0.0
        exceed += sim_ratio >= ratio
    p_value = (exceed + 1) / (simulations + 1)
    return {
        "dominantPeriodYears": _finite(dominant_period, 2),
        "bandPowerShare": _finite(ratio),
        "redNoisePValue": _finite(p_value),
        "significantAt10Pct": bool(p_value < 0.10),
        "ar1": _finite(phi),
    }


def _state(wave: np.ndarray) -> dict[str, Any]:
    level = float(wave[-1])
    momentum = float(wave[-1] - np.mean(wave[-6:-1]))
    momentum_label = "改善" if momentum > 0.12 else "走弱" if momentum < -0.12 else "平稳"
    return {
        "level": _finite(level),
        "momentum": _finite(momentum),
        "levelLabel": "位置未校准",
        "momentumLabel": momentum_label,
        "label": f"位置未校准 · 动量{momentum_label}",
        "caveat": "滤波分量正负号及端点水平不能直接解释为康波繁荣或萧条阶段。",
    }


def _same_level(left: float, right: float) -> bool:
    return (left >= 0) == (right >= 0)


def _same_momentum(left: np.ndarray, right: np.ndarray) -> bool:
    return (left[-1] - np.mean(left[-6:-1]) >= 0) == (right[-1] - np.mean(right[-6:-1]) >= 0)


def _stability(
    family_panel: pd.DataFrame,
    weights: pd.Series,
    composite: pd.Series,
    ensemble: np.ndarray,
    methods: dict[str, np.ndarray],
) -> dict[str, Any]:
    method_level = np.mean([_same_level(values[-1], ensemble[-1]) for values in methods.values()])
    method_momentum = np.mean([_same_momentum(values, ensemble) for values in methods.values()])
    ablations = []
    for family in family_panel.columns:
        remaining = family_panel.drop(columns=family)
        ablated, _ = _weighted_composite(remaining, weights.drop(index=family))
        ablated = ablated.interpolate(limit=3, limit_area="inside")
        wave, _ = _ensemble_wave(ablated)
        ablations.append({
            "excludedFamily": family,
            "levelMatches": bool(_same_level(wave[-1], ensemble[-1])),
            "momentumMatches": bool(_same_momentum(wave, ensemble)),
            "state": _state(wave),
        })
    cutoff_rows = []
    for cutoff in (1850, 1900, 1950, 2000, 2020):
        truncated = composite.loc[:cutoff]
        if len(truncated) < 120:
            continue
        truncated_wave, _ = _ensemble_wave(truncated)
        reference_index = composite.index.get_loc(cutoff)
        reference = ensemble[: reference_index + 1]
        cutoff_rows.append({
            "cutoff": cutoff,
            "levelMatches": bool(_same_level(truncated_wave[-1], reference[-1])),
            "momentumMatches": bool(_same_momentum(truncated_wave, reference)),
        })
    return {
        "methodLevelAgreement": _finite(method_level),
        "methodMomentumAgreement": _finite(method_momentum),
        "leaveOneFamilyOutLevelAgreement": _finite(np.mean([row["levelMatches"] for row in ablations])),
        "leaveOneFamilyOutMomentumAgreement": _finite(np.mean([row["momentumMatches"] for row in ablations])),
        "cutoffLevelAgreement": _finite(np.mean([row["levelMatches"] for row in cutoff_rows])),
        "cutoffMomentumAgreement": _finite(np.mean([row["momentumMatches"] for row in cutoff_rows])),
        "familyAblations": ablations,
        "cutoffs": cutoff_rows,
    }


def _wilson_interval(successes: int, total: int, z: float = 1.6448536269514722) -> list[float | None]:
    if total == 0:
        return [None, None]
    probability = successes / total
    denominator = 1.0 + z**2 / total
    center = (probability + z**2 / (2.0 * total)) / denominator
    margin = z * math.sqrt(probability * (1.0 - probability) / total + z**2 / (4.0 * total**2)) / denominator
    return [_finite(center - margin), _finite(center + margin)]


def _direction_features(smooth: pd.Series, year: int) -> list[float] | None:
    if year - 20 not in smooth.index:
        return None
    features = [
        smooth.loc[year],
        smooth.loc[year] - smooth.loc[year - 5],
        smooth.loc[year] - smooth.loc[year - 10],
        smooth.loc[year] - smooth.loc[year - 20],
        smooth.loc[year - 9 : year].std(),
        smooth.loc[year - 19 : year].mean(),
    ]
    return [float(value) for value in features] if np.all(np.isfinite(features)) else None


def _direction_validation(composite: pd.Series, horizon: int) -> dict[str, Any]:
    smooth = composite.rolling(5, min_periods=3).mean()
    examples = []
    for year in range(int(smooth.index.min()) + 20, END_YEAR - horizon + 1):
        features = _direction_features(smooth, year)
        target = float(smooth.loc[year + horizon] - smooth.loc[year])
        if features is not None and math.isfinite(target) and abs(target) >= 0.03:
            examples.append({"year": year, "features": features, "target": target})
    rows = []
    for origin in range(1900, END_YEAR - horizon + 1, horizon):
        train = [row for row in examples if row["year"] + horizon <= origin]
        current = next((row for row in examples if row["year"] == origin), None)
        if len(train) < 50 or current is None:
            continue
        model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
        model.fit(
            np.asarray([row["features"] for row in train]),
            np.asarray([row["target"] for row in train]),
        )
        change = float(model.predict(np.asarray([current["features"]]))[0])
        predicted = 1 if change >= 0 else -1
        actual_change = current["target"]
        actual = 1 if actual_change >= 0 else -1
        past_change = float(smooth.loc[origin] - smooth.loc[origin - horizon])
        baseline = 1 if past_change >= 0 else -1
        rows.append({
            "origin": origin,
            "predicted": predicted,
            "actual": actual,
            "correct": bool(predicted == actual),
            "baselineCorrect": bool(baseline == actual),
            "forecastChange": change,
            "actualChange": actual_change,
        })
    successes = sum(row["correct"] for row in rows)
    baseline_successes = sum(row["baselineCorrect"] for row in rows)
    latest_features = _direction_features(smooth, END_YEAR)
    available = [row for row in examples if row["year"] + horizon <= END_YEAR]
    current_model = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
    current_model.fit(
        np.asarray([row["features"] for row in available]),
        np.asarray([row["target"] for row in available]),
    )
    current_change = float(current_model.predict(np.asarray([latest_features]))[0]) if latest_features else 0.0
    recent_rows = [row for row in rows if row["origin"] >= 1950]
    return {
        "horizonYears": horizon,
        "sampleCount": len(rows),
        "accuracy": _finite(successes / len(rows) if rows else None),
        "wilson90": _wilson_interval(successes, len(rows)),
        "inertiaBaselineAccuracy": _finite(baseline_successes / len(rows) if rows else None),
        "accuracyLift": _finite((successes - baseline_successes) / len(rows) if rows else None),
        "recentSince1950Count": len(recent_rows),
        "recentSince1950Accuracy": _finite(np.mean([row["correct"] for row in recent_rows]) if recent_rows else None),
        "nonOverlappingOrigins": True,
        "model": "扩展窗口 Ridge；仅使用当时可见的水平、5/10/20年动量与波动特征；固定 alpha=10",
        "currentDirection": "改善" if current_change >= 0 else "走弱",
        "currentForecastChange": _finite(current_change),
        "rows": rows,
    }


def build_validation(*, simulations: int = 500) -> dict[str, Any]:
    panel = pd.read_parquet(PANEL_PATH)
    family_panel, coverage, weights = build_family_panel(panel)
    family_panel = family_panel.loc[START_YEAR:END_YEAR]
    causal_composite, available_weight = _weighted_composite(family_panel, weights)
    causal_composite = causal_composite.interpolate(limit=3, limit_area="inside")
    composite = _robust_z(causal_composite)
    ensemble, methods = _ensemble_wave(composite)
    frequency_rows = []
    for index, family in enumerate(family_panel.columns):
        series = family_panel[family].dropna()
        frequency_rows.append({
            "family": family,
            **_band_power_metrics(series, simulations=simulations, seed=20260811 + index),
        })
    significant_count = sum(row["significantAt10Pct"] for row in frequency_rows)
    dominant_periods = [row["dominantPeriodYears"] for row in frequency_rows]
    direction = [_direction_validation(causal_composite, horizon) for horizon in (5, 10, 20)]
    stability = _stability(family_panel, weights, composite, ensemble, methods)
    state = _state(ensemble)
    frequency_support = significant_count / len(frequency_rows)
    stable_level = min(
        stability["methodLevelAgreement"],
        stability["leaveOneFamilyOutLevelAgreement"],
        stability["cutoffLevelAgreement"],
    )
    stable_momentum = min(
        stability["methodMomentumAgreement"],
        stability["leaveOneFamilyOutMomentumAgreement"],
        stability["cutoffMomentumAgreement"],
    )
    direction_checks = {
        row["horizonYears"]: bool(
            row["sampleCount"] >= 15
            and row["accuracy"] is not None
            and row["wilson90"][0] is not None
            and row["wilson90"][0] > 0.50
            and row["accuracyLift"] is not None
            and row["accuracyLift"] > 0
        )
        for row in direction
        if row["horizonYears"] in {5, 10}
    }
    required_direction_rows = [
        row for row in direction if row["horizonYears"] in {5, 10}
    ]
    qualified_direction_rows = [
        row
        for row in required_direction_rows
        if direction_checks.get(row["horizonYears"], False)
    ]
    direction_agreement = (
        len(required_direction_rows) == 2
        and len({row["currentDirection"] for row in required_direction_rows}) == 1
    )
    direction_supported = (
        len(qualified_direction_rows) == 2 and direction_agreement
    )
    direction_consensus = {
        "status": "supported" if direction_supported else "blocked",
        "requiredHorizonsYears": [5, 10],
        "qualifiedHorizonsYears": [
            row["horizonYears"] for row in qualified_direction_rows
        ],
        "currentDirections": {
            str(row["horizonYears"]): row["currentDirection"]
            for row in direction
            if row["horizonYears"] in {5, 10}
        },
        "crossHorizonAgreement": direction_agreement,
        "reason": (
            "5年与10年方向均通过门槛且当前方向一致。"
            if direction_supported
            else "5年与10年必须同时通过样本、区间和基准门槛，且当前方向一致；当前条件未满足。"
        ),
    }
    full_weight = float(weights.sum())
    current_coverage = float(available_weight.loc[END_YEAR] / full_weight)
    current_bridge_weight = float(
        sum(
            weights[row["family"]]
            for row in coverage
            if row.get("bridgeStatus") == "research_bridge"
        )
    )
    current_direct_coverage = max(0.0, current_coverage - current_bridge_weight / full_weight)
    publishable = (
        stable_level >= 0.60
        and stable_momentum >= 0.60
        and frequency_support >= 0.50
        and current_coverage >= 0.70
        and direction_supported
    )
    conclusion = (
        "康波可作为长期结构背景指示，但不能用于精确峰谷或短期资产预测。"
        if publishable
        else "全球实体核心的35—70年结构、当前覆盖或方向验证尚未同时通过，康波暂仅保留为解释性研究假设。"
    )
    proxy_analysis = build_proxy_analysis(
        panel_path=PANEL_PATH,
        jst_path=JST_PATH,
        bcl_path=BCL_PATH,
    )
    modern_validation = proxy_analysis["modernCrossCountryValidation"]
    asset_relationships = modern_validation.get("relationships", {})
    asset_rows = []
    for name, label in (
        ("equityTotalReturn", "全球股票"),
        ("housingTotalReturn", "全球住房"),
        ("bondTotalReturn", "全球债券"),
    ):
        relationship = asset_relationships.get(name)
        if relationship:
            asset_rows.append(
                {
                    "asset": label,
                    "bandCorrelation": relationship["bandCorrelation"],
                    "bestLagYears": relationship["bestAbsoluteLag"]["lagYears"],
                    "bestLagCorrelation": relationship["bestAbsoluteLag"]["correlation"],
                    "effectiveLongWaves": relationship["effectiveLongWaves"],
                }
            )
    years = composite.index.tolist()
    return {
        "status": "limited" if publishable else "scenario_only",
        "label": "C1 康波长期结构指示",
        "asOf": str(END_YEAR),
        "dates": [str(year) for year in years],
        "composite": [_finite(value) for value in composite.to_numpy()],
        "longWave": [_finite(value) for value in ensemble],
        "methodWaves": {name: [_finite(value) for value in values] for name, values in methods.items()},
        "familySeries": {
            family: [_finite(value) for value in family_panel[family].to_numpy()]
            for family in family_panel.columns
        },
        "currentState": state,
        "coreCoverage": {
            "currentRatio": _finite(current_coverage),
            "currentDirectRatio": _finite(current_direct_coverage),
            "currentBridgeRatio": _finite(current_bridge_weight / full_weight),
            "currentAvailableWeight": _finite(float(available_weight.loc[END_YEAR])),
            "fullWeight": _finite(full_weight),
            "currentFamilies": [
                family for family in family_panel.columns if pd.notna(family_panel.at[END_YEAR, family])
            ],
            "dates": [str(year) for year in available_weight.index],
            "ratios": [_finite(value / full_weight) for value in available_weight.to_numpy()],
        },
        "phaseCalibration": {
            "phase": "萧条末期",
            "transition": "向新周期萌芽阶段过渡",
            "asOf": "2026",
            "status": "manual_research_consensus",
            "basis": "国内康波研究与市场叙事的常见阶段划分，用于解释校准，不覆盖量化检验。",
            "quantitativelyValidated": False,
        },
        "frequencyValidation": {
            "bandYears": list(PERIOD_BAND),
            "significantFamilyCount": significant_count,
            "familyCount": len(frequency_rows),
            "significantFamilyShare": _finite(frequency_support),
            "medianDominantPeriodYears": _finite(float(np.median(dominant_periods)), 2),
            "rangeDominantPeriodYears": [_finite(float(np.min(dominant_periods)), 2), _finite(float(np.max(dominant_periods)), 2)],
            "families": frequency_rows,
            "nullModel": f"AR(1) red noise, {simulations} Monte Carlo simulations",
        },
        "stability": stability,
        "directionValidation": direction,
        "directionConsensus": direction_consensus,
        "familyCoverage": coverage,
        "globalProxyAssessment": proxy_analysis["longSampleProxyAssessment"],
        "financialValidation": modern_validation,
        "strategicAllocationGuidance": {
            "status": "blocked" if not publishable else "limited",
            "horizonYears": [5, 10],
            "signalBudgetCap": 0.25,
            "currentAction": "保持中性，不由C1单独调整资产权重",
            "reason": "1890年以来跨国资产验证只有约2.3个有效长波，股票、住房和债券的领先滞后关系尚不稳定。",
            "researchRelationships": asset_rows,
            "allowedUse": "仅作为长期风险预算和情景分析的辅助输入；必须由C2—C7及估值、利率和风险约束共同确认。",
        },
        "dataGaps": [
            "世界银行现代技术扩散与CHAT仅重叠9年且相关性过低，桥接已拒绝；技术扩散核心暂止于2003年。",
            "1700—1819年主要依赖历史重建的跨国产出，不能发布正式相位。",
        ],
        "publication": {
            "publishable": publishable,
            "claim": conclusion,
            "allowedUses": ["长期结构背景", "低置信动量说明", "明确标注的人工阶段校准"] + (["通过检验的长期方向辅助判断"] if direction_supported else []),
            "blockedUses": ["精确峰谷年份", "短期交易信号", "单一资产收益预测", "固定50年机械外推", "独立资产配置权重"],
        },
        "method": "全球产出、跨国生产率、技术扩散、跨国资本形成、人口、全球连接和全球能源系统七类实体指标加权合成；桥接必须同时满足至少15年重叠和相关系数不低于0.5，未达标则拒绝续接；35—70年频带功率与AR(1)红噪声检验；Gaussian、Butterworth、FFT三滤波器；截断样本与逐家族剔除稳定性；1900年后5/10/20年非重叠递归方向检验。金融资产仅作外部验证。",
        "caveat": conclusion,
        "references": [
            {"title": "Metz (2011), Do Kondratieff waves exist?", "url": "https://doi.org/10.1007/s11698-010-0057-9"},
            {"title": "Korotayev et al. (2010), A Spectral Analysis of World GDP Dynamics", "url": "https://escholarship.org/content/qt9jv108xp/qt9jv108xp.pdf"},
            {"title": "Perez (2009), Technological revolutions and techno-economic paradigms", "url": "https://doi.org/10.1093/cje/bep051"},
            {"title": "Comin & Hobijn (2009), The CHAT Dataset", "url": "https://www.nber.org/papers/w15319"},
            {"title": "Jordà-Schularick-Taylor Macrohistory Database", "url": "https://www.macrohistory.net/database/"},
            {"title": "Bergeaud-Cette-Lecat Long-Term Productivity Database", "url": "https://www.longtermproductivity.com/"},
            {"title": "Smil (2017), Energy Transitions: Global and National Perspectives", "url": "https://ourworldindata.org/energy-production-consumption"},
            {"title": "Baxter & King (1999), Measuring Business Cycles", "url": "https://doi.org/10.1162/003355399556072"},
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--simulations", type=int, default=500)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    payload = build_validation(simulations=args.simulations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output.relative_to(PROJECT_ROOT)),
        "status": payload["status"],
        "currentState": payload["currentState"],
        "frequencyValidation": payload["frequencyValidation"],
        "directionValidation": payload["directionValidation"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
