"""Build causal historical phase candidates and long-sample asset mappings for C2/C3."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
import json
import math
import zipfile

import numpy as np
import pandas as pd
import requests
from scipy.signal import find_peaks
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from seven_cycle_platform.cycles import adaptive_harmonic_state_filter

try:
    from scripts.research_c2_c3_long_panel import (
        CYCLE_SPECS,
        JST_COUNTRIES,
        _align_bridge_factor,
        _fetch_bis,
        _fetch_oecd_gfcf,
        _fetch_oecd_house_prices,
        _fetch_world_bank,
        _load_jst,
        _same_quarter_gfcf_feature,
        _same_quarter_house_feature,
        build_bridge_panel,
        build_c2_partial_year_panel,
        build_c3_partial_year_panel,
        build_jst_panel,
        causal_robust_z,
        validate_c2_partial_year_bridge,
        validate_c3_partial_year_bridge,
    )
except ModuleNotFoundError:
    from research_c2_c3_long_panel import (  # type: ignore[no-redef]
        CYCLE_SPECS,
        JST_COUNTRIES,
        _align_bridge_factor,
        _fetch_bis,
        _fetch_oecd_gfcf,
        _fetch_oecd_house_prices,
        _fetch_world_bank,
        _load_jst,
        _same_quarter_gfcf_feature,
        _same_quarter_house_feature,
        build_bridge_panel,
        build_c2_partial_year_panel,
        build_c3_partial_year_panel,
        build_jst_panel,
        causal_robust_z,
        validate_c2_partial_year_bridge,
        validate_c3_partial_year_bridge,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "c2_c3_historical_mapping"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c2_c3_historical_mapping.json"

FF_URLS = {
    "ff48": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/48_Industry_Portfolios_CSV.zip",
    "ff25": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/25_Portfolios_5x5_CSV.zip",
}

PHASE_LABELS = {
    "recovery": "复苏",
    "expansion": "扩张",
    "slowdown": "放缓",
    "contraction": "收缩",
}
PHASE_ORDER = tuple(PHASE_LABELS)
PHASE_PROBABILITY_PRIOR_STRENGTH = 4.0
PHASE_PROBABILITY_PRIMARY_PRIOR = 0.80
PHASE_PROBABILITY_OPPOSITE_PRIOR = 0.02
PHASE_PROBABILITY_MINIMUM_HISTORY = 12
ASSET_RISK_BOOTSTRAP_DRAWS = 5_000
ASSET_RISK_WEIGHT_GRID = (0.0, 0.10, 0.25)
ASSET_RISK_WEIGHT_MAE_RELATIVE_TOLERANCE = 0.0
ASSET_RISK_DEVELOPMENT_END_YEAR = 2020
ASSET_RISK_HOLDOUT_START_YEAR = 2021
FRED_CPI_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"

RETURN_FAMILIES = {
    "C2": set(),
    "C3": {"family_equity_return3"},
}

C2_GEOGRAPHIC_REGIONS = {
    "north_america": {
        "label": "北美",
        "isos": ("CAN", "USA"),
        "minimumCountries": 2,
    },
    "europe": {
        "label": "欧洲",
        "isos": (
            "BEL",
            "CHE",
            "DEU",
            "DNK",
            "ESP",
            "FIN",
            "FRA",
            "GBR",
            "IRL",
            "ITA",
            "NLD",
            "NOR",
            "PRT",
            "SWE",
        ),
        "minimumCountries": 6,
    },
    "asia_pacific": {
        "label": "亚太",
        "isos": ("AUS", "JPN"),
        "minimumCountries": 2,
    },
}
C2_ISO_REGION = {
    iso: region_id
    for region_id, region in C2_GEOGRAPHIC_REGIONS.items()
    for iso in region["isos"]
}
C2_GEOGRAPHIC_MINIMUM_COUNTRY_OBSERVATIONS = 60
C2_GEOGRAPHIC_MINIMUM_ASSETS = 100
C2_GEOGRAPHIC_VALIDATION_CELLS = {
    "1yReturn": (1, "return", "未来1年收益"),
    "3yReturn": (3, "return", "未来3年收益"),
    "1yRisk": (1, "risk", "未来1年风险"),
    "3yRisk": (3, "risk", "未来3年风险"),
}


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _wilson_interval(successes: int, observations: int) -> list[object]:
    if observations <= 0:
        return [None, None]
    z = 1.6448536269514722
    probability = successes / observations
    denominator = 1.0 + z**2 / observations
    center = (probability + z**2 / (2.0 * observations)) / denominator
    radius = (
        z
        * math.sqrt(
            probability * (1.0 - probability) / observations
            + z**2 / (4.0 * observations**2)
        )
        / denominator
    )
    return [_json_value(max(0.0, center - radius)), _json_value(min(1.0, center + radius))]


def _download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 1_000:
        return destination
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=180)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return destination


def _persistent_sign(series: pd.Series, deadband: float) -> pd.Series:
    state = 0
    result: list[int] = []
    for value in pd.to_numeric(series, errors="coerce"):
        if not np.isfinite(value):
            result.append(state)
            continue
        if value > deadband:
            state = 1
        elif value < -deadband:
            state = -1
        elif state == 0:
            state = 1 if value >= 0 else -1
        result.append(state)
    return pd.Series(result, index=series.index, dtype="int64")


def _persistent_sign_with_band(
    series: pd.Series,
    deadband: pd.Series,
) -> pd.Series:
    state = 0
    result: list[int] = []
    aligned_band = deadband.reindex(series.index)
    for value, threshold in zip(
        pd.to_numeric(series, errors="coerce"),
        pd.to_numeric(aligned_band, errors="coerce"),
        strict=True,
    ):
        if not np.isfinite(value):
            result.append(state)
            continue
        bounded_threshold = float(threshold) if np.isfinite(threshold) else 0.0
        if value > bounded_threshold:
            state = 1
        elif value < -bounded_threshold:
            state = -1
        elif state == 0:
            state = 1 if value >= 0 else -1
        result.append(state)
    return pd.Series(result, index=series.index, dtype="int64")


def _phase_name(level_sign: int, slope_sign: int) -> str:
    if level_sign < 0 and slope_sign >= 0:
        return "recovery"
    if level_sign >= 0 and slope_sign >= 0:
        return "expansion"
    if level_sign >= 0 and slope_sign < 0:
        return "slowdown"
    return "contraction"


def build_macro_only_panel(jst: pd.DataFrame, cycle_id: str) -> pd.DataFrame:
    panel = build_jst_panel(jst, cycle_id)
    family_columns = [
        column
        for column in panel.columns
        if column.startswith("family_") and column not in RETURN_FAMILIES[cycle_id]
    ]
    factor_columns = family_columns
    if cycle_id == "C2":
        factor_columns = [
            column
            for column in ("family_housing_momentum", "family_mortgage_credit")
            if column in panel.columns
        ]
    rows: list[pd.DataFrame] = []
    for _, country in panel.groupby("iso"):
        country = country.sort_values("year").copy()
        family_count = country[factor_columns].notna().sum(axis=1)
        required = 2 if cycle_id == "C2" else 2
        factor = country[factor_columns].mean(axis=1, skipna=True).where(
            family_count >= required
        )
        country["factor"] = factor.ewm(
            span=CYCLE_SPECS[cycle_id].smoothing_span,
            adjust=False,
            min_periods=2,
        ).mean()
        rows.append(country[["iso", "year", "factor", *family_columns]])
    return pd.concat(rows, ignore_index=True)


def _global_factor(panel: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    pivot = panel.pivot_table(index="year", columns="iso", values="factor", aggfunc="last")
    factor = pivot.median(axis=1, skipna=True).where(pivot.notna().sum(axis=1) >= 6).dropna()
    country_count = pivot.notna().sum(axis=1).reindex(factor.index).astype(int)
    return factor, country_count


def _c2_structural_position(jst: pd.DataFrame) -> dict[str, object]:
    rows: list[pd.DataFrame] = []
    for iso, group in jst.groupby("iso"):
        country = group.sort_values("year").set_index("year")
        nominal_gdp = pd.to_numeric(country["gdp"], errors="coerce").where(
            lambda value: value > 0
        )
        rental_yield = pd.to_numeric(
            country["housing_rent_yd"], errors="coerce"
        ).where(lambda value: value > 0)
        frame = pd.DataFrame(index=country.index)
        frame["valuation"] = causal_robust_z(-np.log(rental_yield))
        frame["mortgageLeverage"] = causal_robust_z(
            pd.to_numeric(country["tmort"], errors="coerce") / nominal_gdp
        )
        frame["investmentLevel"] = causal_robust_z(
            pd.to_numeric(country["iy"], errors="coerce")
        )
        frame["iso"] = iso
        frame["year"] = frame.index.astype(int)
        rows.append(frame.reset_index(drop=True))
    panel = pd.concat(rows, ignore_index=True)
    latest_year = int(panel["year"].max())
    current = panel.loc[panel["year"] == latest_year]
    channels = {
        "valuation": "房价估值",
        "mortgageLeverage": "按揭杠杆",
        "investmentLevel": "投资水平",
    }
    values = {
        channel: float(pd.to_numeric(current[channel], errors="coerce").median())
        for channel in channels
    }
    labels = {
        channel: "偏高" if value >= 0.35 else "偏低" if value <= -0.35 else "中性"
        for channel, value in values.items()
    }
    return {
        "asOfYear": latest_year,
        "status": "historical_position_only",
        "channels": [
            {
                "channelId": channel,
                "label": label,
                "value": _json_value(values[channel]),
                "state": labels[channel],
                "countryCount": int(current[channel].notna().sum()),
            }
            for channel, label in channels.items()
        ],
        "summary": " · ".join(
            f"{channels[channel]}{labels[channel]}" for channel in channels
        ),
        "method": "估值、按揭杠杆和投资占比使用各国30年因果稳健标准化后取跨国中位数；只描述结构位置，不参与周期长度选择。",
        "caveat": "结构位置目前止于JST 2020；当前端需等待同口径跨国估值和杠杆桥接验证，不能与2026周期动量直接混称为同一时点。",
    }


def _family_phase_confirmation(
    panel: pd.DataFrame,
    cycle_id: str,
    *,
    aggregate_phase: str,
    aggregate_slope_direction: int,
    aggregate_level_direction: int,
    aggregate_period: float,
    as_of_year: int,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for column in sorted(
        item for item in panel.columns if item.startswith("family_")
    ):
        pivot = panel.pivot_table(
            index="year",
            columns="iso",
            values=column,
            aggfunc="last",
        )
        country_count = pivot.notna().sum(axis=1)
        factor = pivot.median(axis=1, skipna=True).where(country_count >= 6).dropna()
        if len(factor) < 60:
            continue
        current = _adaptive_phase_frame(
            factor,
            country_count.reindex(factor.index),
            cycle_id=cycle_id,
        ).iloc[-1]
        latest_year = int(factor.index.max())
        rows.append(
            {
                "familyId": column.removeprefix("family_"),
                "startYear": int(factor.index.min()),
                "endYear": latest_year,
                "observations": int(len(factor)),
                "latestCountryCount": int(country_count.loc[latest_year]),
                "medianCountryCount": _json_value(country_count.reindex(factor.index).median()),
                "lagYears": int(max(0, as_of_year - latest_year)),
                "currentEligible": latest_year >= as_of_year - 1,
                "phase": str(current["phase"]),
                "levelDirection": int(current["levelDirection"]),
                "slopeDirection": int(current["slopeDirection"]),
                "periodYears": _json_value(current["periodYears"]),
                "periodBoundaryShare": _json_value(
                    current["periodBoundaryShare"]
                ),
                "periodSelectionStrength": _json_value(
                    current["periodSelectionStrength"]
                ),
            }
        )
    current_rows = [row for row in rows if row["currentEligible"]]
    if not current_rows:
        return {
            "status": "unavailable",
            "familyCount": len(rows),
            "currentFamilyCount": 0,
            "families": rows,
        }
    phase_counts = pd.Series([row["phase"] for row in current_rows]).value_counts()
    periods = np.asarray(
        [float(row["periodYears"]) for row in current_rows],
        dtype="float64",
    )
    phase_agreement = float(
        np.mean([row["phase"] == aggregate_phase for row in current_rows])
    )
    slope_agreement = float(
        np.mean(
            [
                int(row["slopeDirection"]) == aggregate_slope_direction
                for row in current_rows
            ]
        )
    )
    level_agreement = float(
        np.mean(
            [
                int(row["levelDirection"]) == aggregate_level_direction
                for row in current_rows
            ]
        )
    )
    consensus = float(phase_counts.iloc[0] / len(current_rows))
    return {
        "status": (
            "confirmed"
            if phase_agreement >= 2 / 3 and slope_agreement >= 2 / 3
            else "mixed"
        ),
        "familyCount": len(rows),
        "currentFamilyCount": len(current_rows),
        "staleFamilyCount": len(rows) - len(current_rows),
        "aggregatePhaseAgreement": _json_value(phase_agreement),
        "aggregateSlopeAgreement": _json_value(slope_agreement),
        "aggregateLevelAgreement": _json_value(level_agreement),
        "majorityPhase": str(phase_counts.index[0]),
        "majorityPhaseShare": _json_value(consensus),
        "periodMedianYears": _json_value(np.median(periods)),
        "periodIqrYears": [
            _json_value(np.quantile(periods, 0.25)),
            _json_value(np.quantile(periods, 0.75)),
        ],
        "aggregatePeriodGapYears": _json_value(
            abs(aggregate_period - float(np.median(periods)))
        ),
        "families": rows,
        "definition": "各指标家族先独立形成跨国中位因子，再分别运行同一因果状态空间模型；只使用更新到当前或上一年的家族确认当前相位。",
    }


def _rebuild_panel_factor_without_family(
    panel: pd.DataFrame,
    cycle_id: str,
    excluded_family: str,
) -> pd.DataFrame:
    family_columns = [
        column
        for column in panel.columns
        if column.startswith("family_") and column != excluded_family
    ]
    factor_columns = family_columns
    minimum_families = 2
    if cycle_id == "C2":
        factor_columns = [
            column
            for column in ("family_housing_momentum", "family_mortgage_credit")
            if column in family_columns
        ]
        minimum_families = 2 if len(factor_columns) == 2 else 1
    rows: list[pd.DataFrame] = []
    for _, country in panel.groupby("iso"):
        country = country.sort_values("year").copy()
        family_count = country[factor_columns].notna().sum(axis=1)
        country["factor"] = (
            country[factor_columns]
            .mean(axis=1, skipna=True)
            .where(family_count >= minimum_families)
            .ewm(
                span=CYCLE_SPECS[cycle_id].smoothing_span,
                adjust=False,
                min_periods=2,
            )
            .mean()
        )
        rows.append(country)
    return pd.concat(rows, ignore_index=True)


def _family_ablation_phase_confirmation(
    historical_panel: pd.DataFrame,
    current_panel: pd.DataFrame,
    cycle_id: str,
    *,
    aggregate_phase: str,
    aggregate_level_direction: int,
    aggregate_slope_direction: int,
) -> dict[str, object]:
    family_columns = sorted(
        column for column in historical_panel.columns if column.startswith("family_")
    )
    rows: list[dict[str, object]] = []
    for excluded_family in family_columns:
        historical = _rebuild_panel_factor_without_family(
            historical_panel,
            cycle_id,
            excluded_family,
        )
        current = _rebuild_panel_factor_without_family(
            current_panel,
            cycle_id,
            excluded_family,
        )
        aligned = _align_bridge_factor(historical, current)
        historical_factor, historical_count = _global_factor(historical)
        bridge_factor, bridge_count = _global_factor(aligned)
        historical_end = int(historical_factor.index.max())
        extension = bridge_factor.loc[bridge_factor.index > historical_end]
        combined_factor = pd.concat([historical_factor, extension]).sort_index()
        combined_count = pd.concat(
            [historical_count, bridge_count.reindex(extension.index)]
        ).reindex(combined_factor.index)
        latest = _adaptive_phase_frame(
            combined_factor,
            combined_count,
            cycle_id=cycle_id,
        ).iloc[-1]
        rows.append(
            {
                "excludedFamily": excluded_family.removeprefix("family_"),
                "role": (
                    "core"
                    if cycle_id == "C2"
                    and excluded_family
                    in {"family_housing_momentum", "family_mortgage_credit"}
                    else "confirmation"
                    if cycle_id == "C2"
                    else "core"
                ),
                "phase": str(latest["phase"]),
                "levelDirection": int(latest["levelDirection"]),
                "slopeDirection": int(latest["slopeDirection"]),
                "periodYears": _json_value(latest["periodYears"]),
            }
        )
    phase_agreement = float(
        np.mean([row["phase"] == aggregate_phase for row in rows])
    )
    slope_agreement = float(
        np.mean(
            [
                int(row["slopeDirection"]) == aggregate_slope_direction
                for row in rows
            ]
        )
    )
    level_agreement = float(
        np.mean(
            [
                int(row["levelDirection"])
                == aggregate_level_direction
                for row in rows
            ]
        )
    )
    return {
        "status": (
            "stable"
            if phase_agreement >= 0.80 and slope_agreement >= 0.80
            else "sensitive"
        ),
        "tests": len(rows),
        "phaseAgreement": _json_value(phase_agreement),
        "levelAgreement": _json_value(level_agreement),
        "slopeAgreement": _json_value(slope_agreement),
        "results": rows,
        "definition": "每次剔除一个指标家族后，重新构造历史因子、重新完成跨源尺度校准，再判断当前相位；不复用原合成因子的尺度。",
    }


def _governed_broad_state(
    current: dict[str, object],
    family_confirmation: dict[str, object],
    family_ablation: dict[str, object],
) -> dict[str, object]:
    level_agreement = float(
        np.mean(
            [
                float(family_confirmation.get("aggregateLevelAgreement") or 0.0),
                float(family_ablation.get("levelAgreement") or 0.0),
            ]
        )
    )
    slope_agreement = float(
        np.mean(
            [
                float(family_confirmation.get("aggregateSlopeAgreement") or 0.0),
                float(family_ablation.get("slopeAgreement") or 0.0),
            ]
        )
    )
    level = (
        "above_trend"
        if int(current["levelDirection"]) >= 0
        else "below_trend"
    )
    momentum = "rising" if int(current["slopeDirection"]) >= 0 else "falling"
    slope_signal_to_uncertainty = abs(float(current["slope"])) / max(
        float(current["uncertainty"]),
        1e-8,
    )
    governed_level = level if level_agreement >= 2 / 3 else "mixed"
    governed_momentum = (
        momentum
        if slope_agreement >= 2 / 3
        and slope_signal_to_uncertainty >= 0.10
        else "mixed"
    )
    level_label = {
        "above_trend": "高位",
        "below_trend": "低位",
        "mixed": "高低位分歧",
    }[governed_level]
    momentum_label = {
        "rising": "动量上行",
        "falling": "动量下行",
        "mixed": "动量分歧",
    }[governed_momentum]
    return {
        "status": "limited_broad_state" if governed_level != "mixed" else "blocked",
        "level": governed_level,
        "momentum": governed_momentum,
        "label": f"{level_label} · {momentum_label}",
        "levelAgreement": _json_value(level_agreement),
        "momentumAgreement": _json_value(slope_agreement),
        "momentumSignalToUncertainty": _json_value(
            slope_signal_to_uncertainty
        ),
        "exactPhase": str(current["phase"]),
        "method": "把四相位拆成周期水平与动量两个判断；家族稳定率达到三分之二且斜率超过状态不确定性的10%，才发布动量方向。",
        "caveat": "宽状态用于保留稳定的高低位信息；动量分歧时不把复苏、扩张、放缓或收缩作为正式结论。",
    }


def _adaptive_phase_frame(
    factor: pd.Series,
    country_count: pd.Series,
    *,
    cycle_id: str,
) -> pd.DataFrame:
    spec = CYCLE_SPECS[cycle_id]
    state = adaptive_harmonic_state_filter(
        factor,
        period_min=spec.search_band_years[0],
        period_max=spec.search_band_years[1],
        period_step=0.5,
        score_window=80,
        min_score_observations=40,
    )
    level_scale = state.level.expanding(min_periods=20).std(ddof=0).shift(1)
    slope_scale = state.slope.expanding(min_periods=20).std(ddof=0).shift(1)
    level_deadband = (level_scale * 0.08).clip(lower=0.015).fillna(0.0)
    slope_deadband = (slope_scale * 0.08).clip(lower=0.004).fillna(0.0)
    level_sign = _persistent_sign_with_band(state.level, level_deadband)
    slope_sign = _persistent_sign_with_band(state.slope, slope_deadband)
    phase = pd.Series(
        [
            _phase_name(int(level_sign.loc[year]), int(slope_sign.loc[year]))
            for year in factor.index
        ],
        index=factor.index,
    )
    period_width = spec.search_band_years[1] - spec.search_band_years[0]
    period_dispersion = (
        1.0 - (state.period_high - state.period_low) / period_width
    ).clip(0.0, 1.0)
    signal_to_uncertainty = (
        state.amplitude / state.uncertainty.replace(0.0, np.nan)
    ).fillna(0.0)
    confidence = (
        0.15
        + 0.30 * state.phase_agreement
        + 0.20 * np.minimum(1.0, signal_to_uncertainty / 2.0)
        + 0.15 * period_dispersion
        + 0.05 * state.selection_strength
        + 0.15 * np.minimum(1.0, country_count / len(JST_COUNTRIES))
    ).clip(0.0, 0.90)
    return pd.DataFrame(
        {
            "year": factor.index.astype(int),
            "rawValue": factor.to_numpy(),
            "trend": state.trend.to_numpy(),
            "trendSlope": state.trend_slope.to_numpy(),
            "value": state.level.to_numpy(),
            "quadrature": state.quadrature.to_numpy(),
            "slope": state.slope.to_numpy(),
            "amplitude": state.amplitude.to_numpy(),
            "angle": state.angle.to_numpy(),
            "uncertainty": state.uncertainty.to_numpy(),
            "periodYears": state.period.to_numpy(),
            "periodLowYears": state.period_low.to_numpy(),
            "periodHighYears": state.period_high.to_numpy(),
            "phaseAgreement": state.phase_agreement.to_numpy(),
            "periodBoundaryShare": state.boundary_share.to_numpy(),
            "periodSelectionStrength": state.selection_strength.to_numpy(),
            "levelDirection": level_sign.to_numpy(),
            "slopeDirection": slope_sign.to_numpy(),
            "phase": phase.to_numpy(),
            "confidence": confidence.to_numpy(),
            "countryCount": country_count.reindex(factor.index).astype(int).to_numpy(),
        }
    )


def build_phase_history(jst: pd.DataFrame, cycle_id: str) -> pd.DataFrame:
    panel = build_macro_only_panel(jst, cycle_id)
    factor, country_count = _global_factor(panel)
    return _adaptive_phase_frame(
        factor,
        country_count,
        cycle_id=cycle_id,
    )


def _c2_geographic_phase_frames(
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    country_rows: list[pd.DataFrame] = []
    for iso, country in panel.groupby("iso"):
        factor = (
            country.sort_values("year")
            .set_index("year")["factor"]
            .dropna()
        )
        if len(factor) < C2_GEOGRAPHIC_MINIMUM_COUNTRY_OBSERVATIONS:
            continue
        state = _adaptive_phase_frame(
            factor,
            pd.Series(1, index=factor.index),
            cycle_id="C2",
        )
        state["iso"] = str(iso)
        state["regionId"] = C2_ISO_REGION[str(iso)]
        country_rows.append(state)
    country_history = pd.concat(country_rows, ignore_index=True)

    region_rows: list[pd.DataFrame] = []
    for region_id, region in C2_GEOGRAPHIC_REGIONS.items():
        pivot = panel.loc[panel["iso"].isin(region["isos"])].pivot_table(
            index="year",
            columns="iso",
            values="factor",
            aggfunc="last",
        )
        country_count = pivot.notna().sum(axis=1)
        factor = pivot.median(axis=1, skipna=True).where(
            country_count >= int(region["minimumCountries"])
        ).dropna()
        state = _adaptive_phase_frame(
            factor,
            country_count.reindex(factor.index),
            cycle_id="C2",
        )
        state["regionId"] = region_id
        state["regionLabel"] = str(region["label"])
        region_rows.append(state)
    region_history = pd.concat(region_rows, ignore_index=True)
    return country_history, region_history


def build_c2_geographic_state(
    jst: pd.DataFrame,
    *,
    spp: pd.DataFrame,
    total_credit: pd.DataFrame,
    world_bank: pd.DataFrame,
    oecd_house_prices: pd.DataFrame,
    global_candidate: dict[str, object],
) -> dict[str, object]:
    historical_panel = build_macro_only_panel(jst, "C2")
    historical_end = int(historical_panel.loc[historical_panel["factor"].notna(), "year"].max())
    annual_bridge = build_bridge_panel(
        "C2",
        spp=spp,
        total_credit=total_credit,
        world_bank=world_bank,
        oecd_house_prices=oecd_house_prices,
    )
    partial_panel, partial_metadata = build_c2_partial_year_panel(
        annual_bridge,
        spp,
        oecd_house_prices,
    )
    aligned_partial = _align_bridge_factor(historical_panel, partial_panel)
    combined_panel = pd.concat(
        [
            historical_panel.loc[historical_panel["year"] <= historical_end],
            aligned_partial.loc[aligned_partial["year"] > historical_end],
        ],
        ignore_index=True,
        sort=False,
    )
    country_history, region_history = _c2_geographic_phase_frames(combined_panel)
    country_names = (
        jst[["iso", "country"]]
        .drop_duplicates("iso")
        .set_index("iso")["country"]
        .astype(str)
        .to_dict()
    )
    current_year = int(str(partial_metadata["asOfPeriod"])[:4])
    current_countries = (
        country_history.sort_values(["iso", "year"])
        .groupby("iso", as_index=False)
        .tail(1)
        .copy()
    )
    current_regions = (
        region_history.sort_values(["regionId", "year"])
        .groupby("regionId", as_index=False)
        .tail(1)
        .copy()
    )
    global_current = global_candidate["current"]
    global_phase = str(global_current["phase"])
    global_slope_direction = int(global_current["slopeDirection"])
    country_phase_agreement = float(
        (current_countries["phase"] == global_phase).mean()
    )
    country_slope_agreement = float(
        (current_countries["slopeDirection"] == global_slope_direction).mean()
    )
    region_phase_agreement = float(
        (current_regions["phase"] == global_phase).mean()
    )
    region_slope_agreement = float(
        (current_regions["slopeDirection"] == global_slope_direction).mean()
    )
    country_phase_counts = current_countries["phase"].value_counts().to_dict()
    region_phase_counts = current_regions["phase"].value_counts().to_dict()

    country_current_rows = []
    for row in current_countries.to_dict(orient="records"):
        country_current_rows.append(
            {
                "iso": str(row["iso"]),
                "name": country_names.get(str(row["iso"]), str(row["iso"])),
                "regionId": str(row["regionId"]),
                "asOfYear": int(row["year"]),
                "staleYears": int(max(0, current_year - int(row["year"]))),
                "phase": str(row["phase"]),
                "levelDirection": int(row["levelDirection"]),
                "slopeDirection": int(row["slopeDirection"]),
                "periodYears": _json_value(row["periodYears"]),
                "confidence": _json_value(row["confidence"]),
            }
        )
    region_current_rows = []
    for row in current_regions.to_dict(orient="records"):
        region_current_rows.append(
            {
                "regionId": str(row["regionId"]),
                "label": str(row["regionLabel"]),
                "asOfYear": int(row["year"]),
                "staleYears": int(max(0, current_year - int(row["year"]))),
                "phase": str(row["phase"]),
                "levelDirection": int(row["levelDirection"]),
                "slopeDirection": int(row["slopeDirection"]),
                "periodYears": _json_value(row["periodYears"]),
                "confidence": _json_value(row["confidence"]),
                "countryCount": int(row["countryCount"]),
            }
        )

    country_history_columns = [
        "iso",
        "regionId",
        "year",
        "phase",
        "value",
        "slope",
        "periodYears",
        "levelDirection",
        "slopeDirection",
    ]
    region_history_columns = [
        "regionId",
        "regionLabel",
        "year",
        "phase",
        "value",
        "slope",
        "periodYears",
        "levelDirection",
        "slopeDirection",
        "countryCount",
    ]
    return {
        "status": "research_only",
        "formalStatus": "blocked",
        "asOfPeriod": partial_metadata["asOfPeriod"],
        "globalCandidatePhase": global_phase,
        "globalCandidateSlopeDirection": global_slope_direction,
        "currentCountries": country_current_rows,
        "currentRegions": region_current_rows,
        "countryHistory": _records(country_history[country_history_columns]),
        "regionHistory": _records(region_history[region_history_columns]),
        "summary": {
            "countryCount": int(len(current_countries)),
            "regionCount": int(len(current_regions)),
            "countriesUpdatedInCurrentYear": int(
                (current_countries["year"] == current_year).sum()
            ),
            "countryPhaseAgreementWithGlobal": _json_value(
                country_phase_agreement
            ),
            "countrySlopeAgreementWithGlobal": _json_value(
                country_slope_agreement
            ),
            "regionPhaseAgreementWithGlobal": _json_value(
                region_phase_agreement
            ),
            "regionSlopeAgreementWithGlobal": _json_value(
                region_slope_agreement
            ),
            "countryPhaseCounts": {
                phase: int(country_phase_counts.get(phase, 0))
                for phase in PHASE_ORDER
            },
            "regionPhaseCounts": {
                phase: int(region_phase_counts.get(phase, 0))
                for phase in PHASE_ORDER
            },
        },
        "method": "各国先用住房动量与按揭信用形成双核心因子，再做同一套因果自适应状态分解；区域状态取区域内国家因子中位数。2021年以后使用已完成跨源尺度对齐的BIS/OECD桥接。",
        "caveat": "国家和区域状态用于识别全球中位数掩盖的错位，不代表每个国家都已通过真实vintage相位验证，也不能直接转化为资产预测。",
    }


def _period_identification(
    factor: pd.Series,
    cycle_id: str,
    current: dict[str, object],
    family_confirmation: dict[str, object] | None = None,
    robustness: dict[str, object] | None = None,
) -> dict[str, object]:
    spec = CYCLE_SPECS[cycle_id]
    boundary_share = float(current["periodBoundaryShare"])
    selection_strength = float(current["periodSelectionStrength"])
    family_phase_agreement = float(
        (family_confirmation or {}).get("aggregatePhaseAgreement") or 0.0
    )
    family_slope_agreement = float(
        (family_confirmation or {}).get("aggregateSlopeAgreement") or 0.0
    )
    if boundary_share >= 0.50:
        status = "boundary_unresolved"
    elif family_phase_agreement < 2 / 3 or family_slope_agreement < 2 / 3:
        status = "family_disagreement"
    elif selection_strength < 0.05:
        status = "weakly_identified"
    else:
        status = "limited_candidate"
    result: dict[str, object] = {
        "status": status,
        "governedSearchBandYears": list(spec.search_band_years),
        "candidateYears": _json_value(current["periodYears"]),
        "candidateRangeYears": (
            robustness["periodRangeYears"]
            if robustness is not None
            else [
                _json_value(current["periodLowYears"]),
                _json_value(current["periodHighYears"]),
            ]
        ),
        "boundaryShare": _json_value(boundary_share),
        "selectionStrength": _json_value(selection_strength),
        "phaseAgreement": _json_value(current["phaseAgreement"]),
        "familyConfirmation": family_confirmation,
        "robustness": robustness,
        "expandedSearch": None,
    }
    if boundary_share < 0.50:
        result["conclusion"] = (
            "指标家族对当前相位或斜率方向未形成三分之二共识，"
            "暂不发布单一精确周期。"
            if status == "family_disagreement"
            else (
                "相位方向在参数集合中一致，但周期候选间预测似然差异较弱，"
                "暂不发布单一精确周期。"
                if selection_strength < 0.05
                else "动态周期候选具备有限区分度，仍需真实vintage检验。"
            )
        )
        return result

    expanded_band = (8.0, 40.0) if cycle_id == "C2" else (5.0, 24.0)
    expanded = adaptive_harmonic_state_filter(
        factor,
        period_min=expanded_band[0],
        period_max=expanded_band[1],
        period_step=0.5,
        score_window=80,
        min_score_observations=40,
    )
    result["expandedSearch"] = {
        "searchBandYears": list(expanded_band),
        "candidateYears": _json_value(expanded.period.iloc[-1]),
        "candidateRangeYears": [
            _json_value(expanded.period_low.iloc[-1]),
            _json_value(expanded.period_high.iloc[-1]),
        ],
        "boundaryShare": _json_value(expanded.boundary_share.iloc[-1]),
        "selectionStrength": _json_value(expanded.selection_strength.iloc[-1]),
    }
    result["conclusion"] = (
        "治理搜索带已触边；扩围后候选继续外移，但预测似然区分度仍低，"
        "说明当前数据只能支持低频状态方向，不能稳定锁定精确周期长度。"
    )
    return result


def _period_robustness(factor: pd.Series, cycle_id: str) -> dict[str, object]:
    spec = CYCLE_SPECS[cycle_id]
    if cycle_id == "C2":
        specifications = (
            ("governed", 8.0, 28.0, 80, 40),
            ("prior_band", 10.0, 24.0, 80, 40),
            ("narrow_band", 12.0, 24.0, 80, 40),
            ("short_window", 8.0, 28.0, 60, 30),
            ("long_window", 8.0, 28.0, 100, 50),
        )
    else:
        specifications = (
            ("governed", *spec.search_band_years, 80, 40),
            ("short_window", *spec.search_band_years, 60, 30),
            ("long_window", *spec.search_band_years, 100, 50),
        )
    rows: list[dict[str, object]] = []
    for name, period_min, period_max, score_window, minimum in specifications:
        state = adaptive_harmonic_state_filter(
            factor,
            period_min=period_min,
            period_max=period_max,
            period_step=0.5,
            score_window=score_window,
            min_score_observations=minimum,
        )
        rows.append(
            {
                "specification": name,
                "periodYears": _json_value(state.period.iloc[-1]),
                "periodLowYears": _json_value(state.period_low.iloc[-1]),
                "periodHighYears": _json_value(state.period_high.iloc[-1]),
                "levelDirection": int(np.sign(float(state.level.iloc[-1]))),
                "slopeDirection": int(np.sign(float(state.slope.iloc[-1]))),
                "boundaryShare": _json_value(state.boundary_share.iloc[-1]),
                "selectionStrength": _json_value(
                    state.selection_strength.iloc[-1]
                ),
            }
        )
    periods = np.asarray([float(row["periodYears"]) for row in rows])
    slope_directions = [int(row["slopeDirection"]) for row in rows]
    return {
        "status": "period_band_only",
        "specifications": rows,
        "periodMedianYears": _json_value(np.median(periods)),
        "periodRangeYears": [
            _json_value(np.min(periods)),
            _json_value(np.max(periods)),
        ],
        "slopeDirectionAgreement": _json_value(
            max(
                slope_directions.count(-1),
                slope_directions.count(0),
                slope_directions.count(1),
            )
            / len(slope_directions)
        ),
        "boundaryFreeShare": _json_value(
            np.mean([float(row["boundaryShare"]) < 0.50 for row in rows])
        ),
        "conclusion": "多组搜索带和窗口均未触及边界，但周期选择强度仍弱；只发布当前周期范围，不发布精确长度。",
    }


def _turns(phase_history: pd.DataFrame, cycle_id: str) -> list[dict[str, object]]:
    values = phase_history["value"].to_numpy(dtype="float64")
    years = phase_history["year"].to_numpy(dtype="int64")
    distance = 9 if cycle_id == "C2" else 5
    prominence = max(0.08, float(np.nanstd(values)) * 0.22)
    peaks, _ = find_peaks(values, distance=distance, prominence=prominence)
    troughs, _ = find_peaks(-values, distance=distance, prominence=prominence)
    rows = [
        {"year": int(years[index]), "value": _json_value(values[index]), "kind": "peak"}
        for index in peaks
    ] + [
        {"year": int(years[index]), "value": _json_value(values[index]), "kind": "trough"}
        for index in troughs
    ]
    return sorted(rows, key=lambda row: int(row["year"]))


def _run_lengths(phases: pd.Series) -> list[int]:
    if phases.empty:
        return []
    group = phases.ne(phases.shift()).cumsum()
    return phases.groupby(group).size().astype(int).tolist()


def phase_validation(jst: pd.DataFrame, full_history: pd.DataFrame, cycle_id: str) -> dict[str, object]:
    full = full_history.set_index("year")["phase"]
    cutoffs = [year for year in (1950, 1970, 1990, 2010, 2020) if year <= int(full.index.max())]
    comparisons: list[dict[str, object]] = []
    for cutoff in cutoffs:
        truncated = build_phase_history(jst.loc[jst["year"] <= cutoff], cycle_id).set_index("year")["phase"]
        common = full.index.intersection(truncated.index)
        tail = common[common >= cutoff - 9]
        comparisons.append(
            {
                "cutoff": cutoff,
                "historyAgreement": _json_value((full.loc[common] == truncated.loc[common]).mean()),
                "last10YearAgreement": _json_value((full.loc[tail] == truncated.loc[tail]).mean()),
            }
        )
    turns = _turns(full_history, cycle_id)
    intervals: list[int] = []
    for kind in ("peak", "trough"):
        years = [int(row["year"]) for row in turns if row["kind"] == kind]
        intervals.extend(np.diff(years).astype(int).tolist())
    run_lengths = _run_lengths(full_history["phase"])
    macro_panel = build_macro_only_panel(jst, cycle_id)
    latest = full_history.iloc[-1]
    family_confirmation = _family_phase_confirmation(
        macro_panel,
        cycle_id,
        aggregate_phase=str(latest["phase"]),
        aggregate_slope_direction=int(latest["slopeDirection"]),
        aggregate_level_direction=int(latest["levelDirection"]),
        aggregate_period=float(latest["periodYears"]),
        as_of_year=int(latest["year"]),
    )
    return {
        "definition": "宏观综合因子经局部趋势+自适应振荡器状态空间模型分解；动态周期由尾部预测似然选择，参数集合投票后按周期水平与斜率形成四相位。",
        "lookAhead": False,
        "appendOnlyStabilityDefinition": "截断历史一致率只检验因果滤波器在追加新观测后不改写旧状态，不代表相位预测准确率；预测性另由混频历史截点验证衡量。",
        "sourceRevisionCaveat": "截断验证不包含原始统计数据后续修订，真实vintage仍需另建。",
        "cutoffs": comparisons,
        "meanHistoryAgreement": _json_value(np.mean([row["historyAgreement"] for row in comparisons])),
        "medianPhaseRunYears": _json_value(np.median(run_lengths)),
        "turnIntervalMedianYears": _json_value(np.median(intervals) if intervals else None),
        "turnIntervalIqrYears": [
            _json_value(np.quantile(intervals, 0.25) if intervals else None),
            _json_value(np.quantile(intervals, 0.75) if intervals else None),
        ],
        "dynamicPeriodMedianYears": _json_value(full_history["periodYears"].median()),
        "dynamicPeriodIqrYears": [
            _json_value(full_history["periodYears"].quantile(0.25)),
            _json_value(full_history["periodYears"].quantile(0.75)),
        ],
        "latestDynamicPeriodYears": _json_value(full_history["periodYears"].iloc[-1]),
        "latestDynamicPeriodRangeYears": [
            _json_value(full_history["periodLowYears"].iloc[-1]),
            _json_value(full_history["periodHighYears"].iloc[-1]),
        ],
        "latestPhaseAgreement": _json_value(full_history["phaseAgreement"].iloc[-1]),
        "latestPeriodBoundaryShare": _json_value(
            full_history["periodBoundaryShare"].iloc[-1]
        ),
        "latestPeriodSelectionStrength": _json_value(
            full_history["periodSelectionStrength"].iloc[-1]
        ),
        "familyConfirmation": family_confirmation,
    }


def _current_update_isos(
    cycle_id: str,
    *,
    spp: pd.DataFrame,
    oecd_gfcf: pd.DataFrame,
    oecd_house_prices: pd.DataFrame | None = None,
) -> set[str]:
    if cycle_id == "C2":
        real_house = spp.loc[
            (spp["VALUE"] == "R")
            & (pd.to_numeric(spp["UNIT_MEASURE"], errors="coerce") == 628)
        ]
        features = _same_quarter_house_feature(real_house, oecd_house_prices)
        coverage = (
            features.dropna(subset=["family_housing_momentum"])
            .groupby("period")["iso"]
            .nunique()
            .sort_index()
        )
        latest_period = str(coverage.loc[coverage >= 6].index[-1])
        return set(
            features.loc[
                (features["period"] == latest_period)
                & features["family_housing_momentum"].notna(),
                "iso",
            ].astype(str)
        )
    features = _same_quarter_gfcf_feature(oecd_gfcf)
    latest_period = str(features["period"].max())
    return set(
        features.loc[
            (features["period"] == latest_period)
            & features["proxy_investment_impulse3"].notna(),
            "iso",
        ].astype(str)
    )


def _combined_final_factor(
    historical_factor: pd.Series,
    historical_count: pd.Series,
    aligned_annual: pd.DataFrame,
    *,
    year: int,
    historical_end: int,
) -> tuple[pd.Series, pd.Series]:
    bridge_factor, bridge_count = _global_factor(aligned_annual)
    final_factor = historical_factor.loc[
        historical_factor.index <= min(year, historical_end)
    ].copy()
    final_count = historical_count.reindex(final_factor.index).copy()
    extension = bridge_factor.loc[
        (bridge_factor.index > historical_end) & (bridge_factor.index <= year)
    ]
    if not extension.empty:
        final_factor = pd.concat([final_factor, extension])
        final_count = pd.concat([final_count, bridge_count.reindex(extension.index)])
    return final_factor.sort_index(), final_count.reindex(final_factor.sort_index().index)


def _combined_partial_factor(
    historical_factor: pd.Series,
    historical_count: pd.Series,
    aligned_partial: pd.DataFrame,
    *,
    year: int,
    historical_end: int,
) -> tuple[pd.Series, pd.Series] | None:
    partial_factor, partial_count = _global_factor(aligned_partial)
    prior_end = min(year - 1, historical_end)
    current_factor = historical_factor.loc[historical_factor.index <= prior_end].copy()
    current_count = historical_count.reindex(current_factor.index).copy()
    extension = partial_factor.loc[
        (partial_factor.index > historical_end) & (partial_factor.index < year)
    ]
    if not extension.empty:
        current_factor = pd.concat([current_factor, extension])
        current_count = pd.concat([current_count, partial_count.reindex(extension.index)])
    latest = (
        aligned_partial.sort_values(["iso", "year"])
        .groupby("iso", as_index=False)
        .tail(1)
    )
    latest = latest.loc[latest["year"] >= year - 1].dropna(subset=["factor"])
    if len(latest) < 12:
        return None
    current_factor.loc[year] = float(latest["factor"].median())
    current_count.loc[year] = int(len(latest))
    current_factor = current_factor.sort_index()
    return current_factor, current_count.reindex(current_factor.index)


def validate_mixed_frequency_phase(
    historical_panel: pd.DataFrame,
    annual_bridge: pd.DataFrame,
    cycle_id: str,
    *,
    spp: pd.DataFrame,
    oecd_gfcf: pd.DataFrame,
    oecd_house_prices: pd.DataFrame | None = None,
    quarter: int = 1,
) -> dict[str, object]:
    historical_factor, historical_count = _global_factor(historical_panel)
    historical_end = int(historical_factor.index.max())
    update_isos = _current_update_isos(
        cycle_id,
        spp=spp,
        oecd_gfcf=oecd_gfcf,
        oecd_house_prices=oecd_house_prices,
    )
    if cycle_id == "C2":
        available_years = sorted(
            {
                int(period[:4])
                for period in spp["TIME_PERIOD"].astype(str)
                if period.endswith(f"Q{quarter}") and period[:4].isdigit()
            }
        )
        minimum_year = 2000
        confirmed_end_year = int(str(spp["TIME_PERIOD"].astype(str).max())[:4]) - 1
    else:
        features = _same_quarter_gfcf_feature(oecd_gfcf)
        available_years = sorted(features["year"].astype(int).unique())
        minimum_year = 2008
        confirmed_end_year = int(str(features["period"].max())[:4]) - 1

    rows: list[dict[str, object]] = []
    for year in available_years:
        if year < minimum_year or year > confirmed_end_year:
            continue
        annual_cut = annual_bridge.loc[annual_bridge["year"] <= year].copy()
        aligned_annual = _align_bridge_factor(
            historical_panel,
            annual_cut,
            alignment_end_year=min(year, historical_end),
        )
        if cycle_id == "C2":
            partial_panel, metadata = build_c2_partial_year_panel(
                annual_cut,
                spp.loc[spp["TIME_PERIOD"].astype(str) <= f"{year}-Q{quarter}"].copy(),
                (
                    oecd_house_prices.loc[
                        oecd_house_prices["TIME_PERIOD"].astype(str)
                        <= f"{year}-Q{quarter}"
                    ].copy()
                    if oecd_house_prices is not None
                    else None
                ),
                as_of_period=f"{year}-Q{quarter}",
                update_isos=update_isos,
            )
        else:
            partial_panel, metadata = build_c3_partial_year_panel(
                annual_cut,
                oecd_gfcf.loc[
                    oecd_gfcf["TIME_PERIOD"].astype(str) <= f"{year}-Q{quarter}"
                ].copy(),
                as_of_period=f"{year}-Q{quarter}",
                update_isos=update_isos,
            )
        if metadata.get("status") != "limited_partial_year":
            continue
        aligned_partial = _align_bridge_factor(
            historical_panel,
            partial_panel,
            alignment_end_year=min(year - 1, historical_end),
        )
        final_inputs = _combined_final_factor(
            historical_factor,
            historical_count,
            aligned_annual,
            year=year,
            historical_end=historical_end,
        )
        partial_inputs = _combined_partial_factor(
            historical_factor,
            historical_count,
            aligned_partial,
            year=year,
            historical_end=historical_end,
        )
        if partial_inputs is None:
            continue
        final = _adaptive_phase_frame(
            final_inputs[0],
            final_inputs[1],
            cycle_id=cycle_id,
        ).iloc[-1]
        partial = _adaptive_phase_frame(
            partial_inputs[0],
            partial_inputs[1],
            cycle_id=cycle_id,
        ).iloc[-1]
        angle_error = abs(float((final["angle"] - partial["angle"] + 180.0) % 360.0 - 180.0))
        rows.append(
            {
                "year": int(year),
                "finalPhase": str(final["phase"]),
                "q1Phase": str(partial["phase"]),
                "phaseCorrect": int(final["phase"] == partial["phase"]),
                "levelDirectionCorrect": int(
                    int(final["levelDirection"])
                    == int(partial["levelDirection"])
                ),
                "slopeDirectionCorrect": int(
                    int(final["slopeDirection"])
                    == int(partial["slopeDirection"])
                ),
                "angleErrorDegrees": angle_error,
                "periodErrorYears": abs(float(final["periodYears"] - partial["periodYears"])),
                "updatedCountryCount": int(metadata.get("countryCount", 0)),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return {
            "status": "failed",
            "observations": 0,
            "lookAhead": False,
            "reason": "没有足够的混频历史截点。",
        }
    frame["finalTransition"] = frame["finalPhase"].ne(frame["finalPhase"].shift())
    frame.loc[frame.index[0], "finalTransition"] = False
    transitions = frame.loc[frame["finalTransition"]]
    phase_accuracy = float(frame["phaseCorrect"].mean())
    level_accuracy = float(frame["levelDirectionCorrect"].mean())
    slope_accuracy = float(frame["slopeDirectionCorrect"].mean())
    angle_mae = float(frame["angleErrorDegrees"].mean())
    period_mae = float(frame["periodErrorYears"].mean())
    phase_interval = _wilson_interval(int(frame["phaseCorrect"].sum()), len(frame))
    level_interval = _wilson_interval(
        int(frame["levelDirectionCorrect"].sum()),
        len(frame),
    )
    slope_interval = _wilson_interval(
        int(frame["slopeDirectionCorrect"].sum()),
        len(frame),
    )
    transition_interval = _wilson_interval(
        int(transitions["phaseCorrect"].sum()),
        len(transitions),
    )
    broad_state_passed = (
        float(level_interval[0]) >= 0.70
        and float(slope_interval[0]) >= 0.65
    )
    passed = (
        len(frame) >= 12
        and phase_accuracy >= 0.70
        and level_accuracy >= 0.80
        and slope_accuracy >= 0.75
        and angle_mae <= 20.0
        and period_mae <= 2.0
    )
    return {
        "status": "passed_limited" if passed else "failed",
        "lookAhead": False,
        "observations": int(len(frame)),
        "startYear": int(frame["year"].min()),
        "endYear": int(frame["year"].max()),
        "phaseAccuracy": _json_value(phase_accuracy),
        "phaseAccuracyInterval90": phase_interval,
        "levelDirectionAccuracy": _json_value(level_accuracy),
        "levelDirectionAccuracyInterval90": level_interval,
        "slopeDirectionAccuracy": _json_value(slope_accuracy),
        "slopeDirectionAccuracyInterval90": slope_interval,
        "angleMaeDegrees": _json_value(angle_mae),
        "periodMaeYears": _json_value(period_mae),
        "transitionObservations": int(len(transitions)),
        "transitionPhaseAccuracy": _json_value(
            transitions["phaseCorrect"].mean() if not transitions.empty else None
        ),
        "transitionPhaseAccuracyInterval90": transition_interval,
        "broadStateValidation": {
            "status": "passed_limited" if broad_state_passed else "failed",
            "levelLowerBound": level_interval[0],
            "momentumLowerBound": slope_interval[0],
            "gate": {
                "minimumLevelLowerBound90": 0.70,
                "minimumMomentumLowerBound90": 0.65,
            },
            "interpretation": "历史Q1宽状态方向通过不代表当前方向必然清晰；当前是否发布仍由指标家族与逐家族剔除稳定率共同决定。",
        },
        "gate": {
            "minimumObservations": 12,
            "minimumPhaseAccuracy": 0.70,
            "minimumLevelDirectionAccuracy": 0.80,
            "minimumSlopeDirectionAccuracy": 0.75,
            "maximumAngleMaeDegrees": 20.0,
            "maximumPeriodMaeYears": 2.0,
        },
        "history": _records(frame),
        "method": "逐年回放历史Q1：历史因子只保留到上一完整年度，季度住宅价格或实际资本形成更新当年端点；跨源尺度只用当时可见重叠期校准，再与年终完整年度四相位比较。",
        "caveat": "通过代表Q1混频端点可支持研究相位候选，不代表精确相位角、精确拐点或真实发布vintage已经通过。",
    }


def _phase_probability_prior(phase: str) -> np.ndarray:
    phase_index = PHASE_ORDER.index(phase)
    probabilities = np.full(
        len(PHASE_ORDER),
        PHASE_PROBABILITY_OPPOSITE_PRIOR,
        dtype="float64",
    )
    probabilities[phase_index] = PHASE_PROBABILITY_PRIMARY_PRIOR
    probabilities[(phase_index - 1) % len(PHASE_ORDER)] = (
        1.0
        - PHASE_PROBABILITY_PRIMARY_PRIOR
        - PHASE_PROBABILITY_OPPOSITE_PRIOR
    ) / 2.0
    probabilities[(phase_index + 1) % len(PHASE_ORDER)] = (
        1.0
        - PHASE_PROBABILITY_PRIMARY_PRIOR
        - PHASE_PROBABILITY_OPPOSITE_PRIOR
    ) / 2.0
    return probabilities


def _phase_probability_posterior(
    history: pd.DataFrame,
    phase: str,
) -> np.ndarray:
    phase_history = history.loc[history["q1Phase"] == phase]
    counts = (
        phase_history["finalPhase"]
        .value_counts()
        .reindex(PHASE_ORDER, fill_value=0)
        .to_numpy(dtype="float64")
    )
    prior = _phase_probability_prior(phase)
    return (
        counts + PHASE_PROBABILITY_PRIOR_STRENGTH * prior
    ) / (len(phase_history) + PHASE_PROBABILITY_PRIOR_STRENGTH)


def build_phase_probability_calibration(
    cycles: dict[str, object],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for cycle_id in ("C2", "C3"):
        mixed = cycles[cycle_id]["currentPhaseCandidate"]["validation"][
            "mixedFrequencyPhase"
        ]
        for row in mixed["history"]:
            rows.append({**row, "cycleId": cycle_id})
    history = pd.DataFrame(rows).sort_values(["year", "cycleId"]).reset_index(
        drop=True
    )

    validation_rows: list[dict[str, object]] = []
    for _, row in history.iterrows():
        training = history.loc[history["year"] < row["year"]]
        if len(training) < PHASE_PROBABILITY_MINIMUM_HISTORY:
            continue
        probabilities = _phase_probability_posterior(training, str(row["q1Phase"]))
        actual_index = PHASE_ORDER.index(str(row["finalPhase"]))
        hard_index = PHASE_ORDER.index(str(row["q1Phase"]))
        actual = np.eye(len(PHASE_ORDER), dtype="float64")[actual_index]
        hard = np.eye(len(PHASE_ORDER), dtype="float64")[hard_index]
        validation_rows.append(
            {
                "cycleId": str(row["cycleId"]),
                "year": int(row["year"]),
                "q1Phase": str(row["q1Phase"]),
                "finalPhase": str(row["finalPhase"]),
                "predictedPhase": PHASE_ORDER[int(np.argmax(probabilities))],
                "top1Correct": int(np.argmax(probabilities) == actual_index),
                "hardTop1Correct": int(hard_index == actual_index),
                "multiclassBrier": float(
                    np.mean((probabilities - actual) ** 2)
                ),
                "hardMulticlassBrier": float(np.mean((hard - actual) ** 2)),
                **{
                    f"probability_{phase}": float(probabilities[index])
                    for index, phase in enumerate(PHASE_ORDER)
                },
            }
        )
    validation_frame = pd.DataFrame(validation_rows)

    def metrics(frame: pd.DataFrame) -> dict[str, object]:
        calibrated_brier = float(frame["multiclassBrier"].mean())
        hard_brier = float(frame["hardMulticlassBrier"].mean())
        return {
            "observations": int(len(frame)),
            "startYear": int(frame["year"].min()),
            "endYear": int(frame["year"].max()),
            "top1Accuracy": _json_value(frame["top1Correct"].mean()),
            "hardTop1Accuracy": _json_value(frame["hardTop1Correct"].mean()),
            "multiclassBrier": _json_value(calibrated_brier),
            "hardMulticlassBrier": _json_value(hard_brier),
            "relativeBrierImprovement": _json_value(
                (hard_brier - calibrated_brier) / hard_brier
                if hard_brier > 1e-12
                else None
            ),
        }

    pooled = metrics(validation_frame)
    by_cycle = {
        cycle_id: metrics(
            validation_frame.loc[validation_frame["cycleId"] == cycle_id]
        )
        for cycle_id in ("C2", "C3")
    }
    passed = (
        pooled["observations"] >= 24
        and float(pooled["relativeBrierImprovement"] or 0.0) >= 0.10
        and all(
            cycle_metrics["observations"] >= 12
            and float(cycle_metrics["multiclassBrier"])
            <= float(cycle_metrics["hardMulticlassBrier"])
            and float(cycle_metrics["top1Accuracy"])
            >= float(cycle_metrics["hardTop1Accuracy"])
            for cycle_metrics in by_cycle.values()
        )
    )

    current: dict[str, object] = {}
    for cycle_id in ("C2", "C3"):
        candidate = cycles[cycle_id]["currentPhaseCandidate"]
        phase = str(candidate["current"]["phase"])
        probabilities = _phase_probability_posterior(history, phase)
        exact_phase_publishable = (
            cycle_id != "C2"
            or (
                candidate.get("exactPhaseStatus") == "limited"
                and candidate.get("governedBroadState", {}).get("momentum")
                != "mixed"
            )
        )
        ranked = sorted(
            zip(PHASE_ORDER, probabilities, strict=True),
            key=lambda item: float(item[1]),
            reverse=True,
        )
        current[cycle_id] = {
            "status": (
                "passed_limited"
                if passed and exact_phase_publishable
                else "blocked_current_disagreement"
                if passed
                else "blocked"
            ),
            "publishable": bool(passed and exact_phase_publishable),
            "asOfPeriod": candidate["asOfPeriod"],
            "primaryPhase": phase,
            "primaryProbability": _json_value(probabilities[PHASE_ORDER.index(phase)]),
            "alternativePhase": ranked[1][0],
            "alternativeProbability": _json_value(ranked[1][1]),
            "probabilities": {
                phase_name: _json_value(probabilities[index])
                for index, phase_name in enumerate(PHASE_ORDER)
            },
            "validation": by_cycle[cycle_id],
            "caveat": (
                "当前指标家族对动量方向未形成共识，因此四相位概率只保留审计值，不对前端发布，也不用于当前资产情景。"
                if passed and not exact_phase_publishable
                else "这是Q1研究相位在年终完整数据下的历史校准概率，不是精确拐点概率；正式相位仍受真实vintage和周期识别门槛约束。"
            ),
        }
        candidate["phaseProbability"] = current[cycle_id]

    return {
        "status": "passed_limited" if passed else "blocked",
        "lookAhead": False,
        "pooledValidation": pooled,
        "cycleValidation": by_cycle,
        "current": current,
        "gate": {
            "minimumPooledObservations": 24,
            "minimumCycleObservations": 12,
            "minimumRelativeBrierImprovement": 0.10,
            "cycleBrierMustNotWorsen": True,
            "cycleTop1AccuracyMustNotWorsen": True,
        },
        "history": _records(validation_frame),
        "method": "C2/C3共享固定Dirichlet先验：当前硬相位80%，两个相邻相位各9%，对侧相位2%；每个历史截点只使用更早年份、且同Q1相位的年终确认结果更新概率。",
        "governance": "概率层只表达部分年度数据导致的相位修订风险，不解锁精确相位角、固定周期长度或精确拐点。",
    }


def _weighted_quantile(
    values: np.ndarray,
    weights: np.ndarray,
    quantile: float,
) -> float:
    order = np.argsort(values)
    ordered_values = values[order]
    ordered_weights = weights[order]
    cumulative = np.cumsum(ordered_weights)
    return float(np.interp(quantile, cumulative, ordered_values))


def _extend_phase_history_for_asset_validation(
    phase_history: pd.DataFrame,
    current_phase_candidate: dict[str, object],
) -> pd.DataFrame:
    mixed = pd.DataFrame(
        current_phase_candidate["validation"]["mixedFrequencyPhase"]["history"]
    )
    extension = mixed[["year", "finalPhase"]].rename(
        columns={"finalPhase": "phase"}
    )
    extension = extension.loc[
        extension["year"] > phase_history["year"].max()
    ]
    return (
        pd.concat([phase_history, extension], ignore_index=True)
        .drop_duplicates("year", keep="last")
        .sort_values("year")
    )


def _prepare_probability_weighted_asset_scenario(
    asset_universe: pd.DataFrame,
    phase_history: pd.DataFrame,
    asset_mapping: dict[str, object],
    phase_probability_calibration: dict[str, object],
    cycle_id: str,
    current_phase_candidate: dict[str, object],
) -> dict[str, object]:
    phase_history = _extend_phase_history_for_asset_validation(
        phase_history,
        current_phase_candidate,
    )
    joined = asset_universe.merge(
        phase_history[["year", "phase"]],
        on="year",
        how="inner",
    ).dropna(subset=["return", "phase"])
    current_probability = phase_probability_calibration["current"][cycle_id]
    phase_probabilities = current_probability["probabilities"]
    mapping_assets = {
        asset["assetId"]: asset for asset in asset_mapping["assets"]
    }

    calibration_history = pd.DataFrame(
        phase_probability_calibration["history"]
    )
    calibration_history = calibration_history.loc[
        calibration_history["cycleId"] == cycle_id
    ].sort_values("year")
    calibration_by_year = {
        int(row["year"]): {
            phase: float(row[f"probability_{phase}"])
            for phase in PHASE_ORDER
        }
        for _, row in calibration_history.iterrows()
    }
    q1_phase_by_year = {
        int(row["year"]): str(row["q1Phase"])
        for _, row in calibration_history.iterrows()
    }

    validation_rows: list[dict[str, object]] = []
    for asset_id, frame in joined.groupby("assetId"):
        frame = frame.sort_values("year")
        for _, current in frame.loc[
            frame["year"].isin(calibration_by_year)
        ].iterrows():
            year = int(current["year"])
            training = frame.loc[frame["year"] < year]
            if len(training) < 30:
                continue
            baseline = float(training["return"].mean())
            baseline_second_moment = float(np.mean(training["return"] ** 2))
            phase_means: dict[str, float] = {}
            phase_second_moments: dict[str, float] = {}
            for phase in PHASE_ORDER:
                phase_returns = training.loc[
                    training["phase"] == phase,
                    "return",
                ]
                phase_means[phase] = (
                    float(phase_returns.mean())
                    if len(phase_returns) >= 3
                    else baseline
                )
                phase_second_moments[phase] = (
                    float(np.mean(phase_returns**2))
                    if len(phase_returns) >= 3
                    else baseline_second_moment
                )
            probabilities = calibration_by_year[year]
            probability_prediction = sum(
                probabilities[phase] * phase_means[phase]
                for phase in PHASE_ORDER
            )
            probability_second_moment = sum(
                probabilities[phase] * phase_second_moments[phase]
                for phase in PHASE_ORDER
            )
            hard_prediction = phase_means[q1_phase_by_year[year]]
            row = {
                "assetId": str(asset_id),
                "year": year,
                "actual": float(current["return"]),
                "probabilityPrediction": probability_prediction,
                "hardPhasePrediction": hard_prediction,
                "unconditionalPrediction": baseline,
                "probabilityRiskPrediction": probability_second_moment,
                "unconditionalRiskPrediction": baseline_second_moment,
            }
            validation_rows.append(row)

    validation_frame = pd.DataFrame(validation_rows)
    return {
        "joined": joined,
        "currentProbability": current_probability,
        "phaseProbabilities": phase_probabilities,
        "mappingAssets": mapping_assets,
        "validationFrame": validation_frame,
    }


def _select_shared_asset_risk_weight(
    prepared_by_cycle: dict[str, dict[str, object]],
) -> dict[str, object]:
    development_frames = []
    for cycle_id, prepared in prepared_by_cycle.items():
        frame = prepared["validationFrame"].copy()
        frame["cycleId"] = cycle_id
        development_frames.append(
            frame.loc[frame["year"] <= ASSET_RISK_DEVELOPMENT_END_YEAR]
        )
    development = pd.concat(development_frames, ignore_index=True)
    development_risk = development["actual"] ** 2
    weight_errors = {
        weight: float(
            (
                development_risk
                - (
                    development["unconditionalRiskPrediction"]
                    + weight
                    * (
                        development["probabilityRiskPrediction"]
                        - development["unconditionalRiskPrediction"]
                    )
                )
            )
            .abs()
            .mean()
        )
        for weight in ASSET_RISK_WEIGHT_GRID
    }
    minimum_weight_error = min(weight_errors.values())
    risk_phase_weight = min(
        weight
        for weight in ASSET_RISK_WEIGHT_GRID
        if weight_errors[weight]
        <= minimum_weight_error
        * (1.0 + ASSET_RISK_WEIGHT_MAE_RELATIVE_TOLERANCE)
    )
    return {
        "phaseWeight": risk_phase_weight,
        "status": "pooled_c2_c3_development_only",
        "endYear": ASSET_RISK_DEVELOPMENT_END_YEAR,
        "observations": int(len(development)),
        "cycleObservations": {
            cycle_id: int((development["cycleId"] == cycle_id).sum())
            for cycle_id in prepared_by_cycle
        },
        "maeByWeight": weight_errors,
    }


def build_probability_weighted_asset_scenario(
    asset_universe: pd.DataFrame,
    phase_history: pd.DataFrame,
    asset_mapping: dict[str, object],
    phase_probability_calibration: dict[str, object],
    cycle_id: str,
    current_phase_candidate: dict[str, object],
    *,
    prepared: dict[str, object] | None = None,
    risk_weight_selection: dict[str, object] | None = None,
) -> dict[str, object]:
    prepared = prepared or _prepare_probability_weighted_asset_scenario(
        asset_universe,
        phase_history,
        asset_mapping,
        phase_probability_calibration,
        cycle_id,
        current_phase_candidate,
    )
    joined = prepared["joined"]
    current_probability = prepared["currentProbability"]
    current_phase_publishable = bool(
        cycle_id != "C2"
        or (
            current_probability.get("publishable")
            and current_phase_candidate.get("governedBroadState", {}).get(
                "momentum"
            )
            != "mixed"
        )
    )
    phase_probabilities = prepared["phaseProbabilities"]
    mapping_assets = prepared["mappingAssets"]
    validation_frame = prepared["validationFrame"].copy()
    if risk_weight_selection is None:
        risk_weight_selection = _select_shared_asset_risk_weight(
            {cycle_id: prepared}
        )
    risk_phase_weight = float(risk_weight_selection["phaseWeight"])
    validation_frame["governedRiskPrediction"] = (
        validation_frame["unconditionalRiskPrediction"]
        + risk_phase_weight
        * (
            validation_frame["probabilityRiskPrediction"]
            - validation_frame["unconditionalRiskPrediction"]
        )
    )
    risk_holdout_asset_ids = set(
        validation_frame.loc[
            validation_frame["year"] >= ASSET_RISK_HOLDOUT_START_YEAR
        ]
        .groupby("assetId")
        .filter(lambda frame: len(frame) >= 3)["assetId"]
        .astype(str)
    )

    asset_validation: dict[str, dict[str, object]] = {}
    for asset_id, validation in validation_frame.groupby("assetId"):
        validation = validation.sort_values("year")
        if len(validation) < 8:
            continue
        probability_mae = float(
            (validation["actual"] - validation["probabilityPrediction"])
            .abs()
            .mean()
        )
        hard_mae = float(
            (validation["actual"] - validation["hardPhasePrediction"])
            .abs()
            .mean()
        )
        unconditional_mae = float(
            (validation["actual"] - validation["unconditionalPrediction"])
            .abs()
            .mean()
        )
        model_error = float(
            np.sum(
                (
                    validation["actual"]
                    - validation["probabilityPrediction"]
                )
                ** 2
            )
        )
        baseline_error = float(
            np.sum(
                (
                    validation["actual"]
                    - validation["unconditionalPrediction"]
                )
                ** 2
            )
        )
        realized_risk = validation["actual"] ** 2
        risk_mae = float(
            (realized_risk - validation["governedRiskPrediction"])
            .abs()
            .mean()
        )
        unconditional_risk_mae = float(
            (realized_risk - validation["unconditionalRiskPrediction"])
            .abs()
            .mean()
        )
        risk_model_error = float(
            np.sum(
                (
                    realized_risk
                    - validation["governedRiskPrediction"]
                )
                ** 2
            )
        )
        risk_baseline_error = float(
            np.sum(
                (
                    realized_risk
                    - validation["unconditionalRiskPrediction"]
                )
                ** 2
            )
        )
        asset_validation[str(asset_id)] = {
            "observations": int(len(validation)),
            "probabilityMae": _json_value(probability_mae),
            "hardPhaseMae": _json_value(hard_mae),
            "unconditionalMae": _json_value(unconditional_mae),
            "beatsHardPhase": probability_mae < hard_mae,
            "beatsUnconditional": probability_mae < unconditional_mae,
            "oosR2VsUnconditional": _json_value(
                1.0 - model_error / baseline_error
                if baseline_error > 1e-12
                else None
            ),
            "riskMae": _json_value(risk_mae),
            "unconditionalRiskMae": _json_value(unconditional_risk_mae),
            "beatsUnconditionalRisk": risk_mae < unconditional_risk_mae,
            "riskOosR2VsUnconditional": _json_value(
                1.0 - risk_model_error / risk_baseline_error
                if risk_baseline_error > 1e-12
                else None
            ),
        }

    scenario_assets: list[dict[str, object]] = []
    for asset_id, frame in joined.groupby("assetId"):
        mapping_asset = mapping_assets.get(str(asset_id))
        if not mapping_asset or not mapping_asset["eligible"]:
            continue
        frame = frame.sort_values("year")
        phase_counts = frame["phase"].value_counts()
        if any(
            phase_probabilities[phase] > 0
            and int(phase_counts.get(phase, 0)) == 0
            for phase in PHASE_ORDER
        ):
            continue
        weights = frame["phase"].map(
            {
                phase: phase_probabilities[phase]
                / max(1, int(phase_counts.get(phase, 0)))
                for phase in PHASE_ORDER
            }
        ).to_numpy(dtype="float64")
        weights = weights / weights.sum()
        returns = frame["return"].to_numpy(dtype="float64")
        expected_return = float(np.sum(weights * returns))
        probability_second_moment = float(np.sum(weights * returns**2))
        unconditional_second_moment = float(np.mean(returns**2))
        governed_risk_second_moment = (
            unconditional_second_moment
            + risk_phase_weight
            * (probability_second_moment - unconditional_second_moment)
        )
        conditional_volatility = float(
            np.sqrt(np.sum(weights * (returns - expected_return) ** 2))
        )
        positive_rate = float(np.sum(weights * (returns > 0)))
        quantile_20 = _weighted_quantile(returns, weights, 0.20)
        tail_mask = returns <= quantile_20
        expected_shortfall_20 = float(
            np.sum(weights[tail_mask] * returns[tail_mask])
            / weights[tail_mask].sum()
        )
        scenario_assets.append(
            {
                "assetId": str(asset_id),
                "category": mapping_asset["category"],
                "name": mapping_asset["name"],
                "dataIdentity": mapping_asset["dataIdentity"],
                "source": mapping_asset["source"],
                "confidence": mapping_asset["confidence"],
                "expectedAnnReturn": _json_value(expected_return),
                "conditionalAnnVol": _json_value(conditional_volatility),
                "governedRiskScale": _json_value(
                    math.sqrt(max(0.0, governed_risk_second_moment))
                ),
                "unconditionalRiskScale": _json_value(
                    math.sqrt(max(0.0, unconditional_second_moment))
                ),
                "riskScaleShiftVsUnconditional": _json_value(
                    math.sqrt(max(0.0, governed_risk_second_moment))
                    - math.sqrt(max(0.0, unconditional_second_moment))
                ),
                "riskValidationEligible": str(asset_id)
                in risk_holdout_asset_ids,
                "positiveRate": _json_value(positive_rate),
                "quantile20Return": _json_value(quantile_20),
                "expectedShortfall20": _json_value(expected_shortfall_20),
                "unconditionalAnnReturn": _json_value(frame["return"].mean()),
                "returnShiftVsUnconditional": _json_value(
                    expected_return - float(frame["return"].mean())
                ),
                "effectiveObservations": _json_value(
                    1.0 / float(np.sum(weights**2))
                ),
                "validation": asset_validation.get(str(asset_id)),
            }
        )

    probability_mae = float(
        (
            validation_frame["actual"]
            - validation_frame["probabilityPrediction"]
        )
        .abs()
        .mean()
    )
    hard_mae = float(
        (
            validation_frame["actual"]
            - validation_frame["hardPhasePrediction"]
        )
        .abs()
        .mean()
    )
    unconditional_mae = float(
        (
            validation_frame["actual"]
            - validation_frame["unconditionalPrediction"]
        )
        .abs()
        .mean()
    )
    validated_assets = list(asset_validation.values())
    share_beating_hard = float(
        np.mean([row["beatsHardPhase"] for row in validated_assets])
    )
    share_beating_unconditional = float(
        np.mean([row["beatsUnconditional"] for row in validated_assets])
    )
    positive_oos_share = float(
        np.mean(
            [
                float(row["oosR2VsUnconditional"] or 0.0) > 0.0
                for row in validated_assets
            ]
        )
    )
    risk_holdout = validation_frame.loc[
        validation_frame["year"] >= ASSET_RISK_HOLDOUT_START_YEAR
    ].copy()
    realized_risk = risk_holdout["actual"] ** 2
    risk_mae = float(
        (realized_risk - risk_holdout["governedRiskPrediction"])
        .abs()
        .mean()
    )
    unconditional_risk_mae = float(
        (realized_risk - risk_holdout["unconditionalRiskPrediction"])
        .abs()
        .mean()
    )
    risk_asset_validation: list[dict[str, object]] = []
    for _, asset_holdout in risk_holdout.groupby("assetId"):
        if len(asset_holdout) < 3:
            continue
        asset_risk = asset_holdout["actual"] ** 2
        model_error = float(
            np.sum(
                (
                    asset_risk
                    - asset_holdout["governedRiskPrediction"]
                )
                ** 2
            )
        )
        baseline_error = float(
            np.sum(
                (
                    asset_risk
                    - asset_holdout["unconditionalRiskPrediction"]
                )
                ** 2
            )
        )
        risk_asset_validation.append(
            {
                "beatsUnconditional": float(
                    (
                        asset_risk
                        - asset_holdout["governedRiskPrediction"]
                    )
                    .abs()
                    .mean()
                )
                < float(
                    (
                        asset_risk
                        - asset_holdout["unconditionalRiskPrediction"]
                    )
                    .abs()
                    .mean()
                ),
                "positiveOosR2": (
                    1.0 - model_error / baseline_error > 0.0
                    if baseline_error > 1e-12
                    else False
                ),
            }
        )
    risk_asset_share = float(
        np.mean(
            [row["beatsUnconditional"] for row in risk_asset_validation]
        )
    )
    risk_positive_oos_share = float(
        np.mean(
            [row["positiveOosR2"] for row in risk_asset_validation]
        )
    )
    risk_year_improvement = (
        risk_holdout.assign(
            riskErrorImprovement=(
                realized_risk
                - risk_holdout["unconditionalRiskPrediction"]
            ).abs()
            - (
                realized_risk
                - risk_holdout["governedRiskPrediction"]
            ).abs()
        )
        .groupby("year")["riskErrorImprovement"]
        .mean()
    )
    risk_positive_year_share = float(
        (risk_year_improvement > 0.0).mean()
    )
    bootstrap_rng = np.random.default_rng(20260804)
    bootstrap_years = risk_year_improvement.index.to_numpy()
    bootstrap_improvements = np.array(
        [
            float(
                risk_year_improvement.loc[
                    bootstrap_rng.choice(
                        bootstrap_years,
                        size=len(bootstrap_years),
                        replace=True,
                    )
                ].mean()
            )
            for _ in range(ASSET_RISK_BOOTSTRAP_DRAWS)
        ],
        dtype="float64",
    )
    risk_bootstrap_probability = float(
        np.mean(bootstrap_improvements > 0.0)
    )
    holdout_weight_sensitivity: dict[str, object] = {}
    for weight in ASSET_RISK_WEIGHT_GRID:
        prediction = (
            risk_holdout["unconditionalRiskPrediction"]
            + weight
            * (
                risk_holdout["probabilityRiskPrediction"]
                - risk_holdout["unconditionalRiskPrediction"]
            )
        )
        model_mae = float((realized_risk - prediction).abs().mean())
        holdout_weight_sensitivity[str(weight)] = {
            "maeImprovementVsUnconditional": _json_value(
                (unconditional_risk_mae - model_mae)
                / unconditional_risk_mae
            )
        }
    passed_vs_hard = (
        probability_mae < hard_mae and share_beating_hard >= 0.75
    )
    beats_unconditional = (
        probability_mae < unconditional_mae
        and share_beating_unconditional >= 0.50
        and positive_oos_share >= 0.50
    )
    risk_passed = (
        len(risk_asset_validation) >= 70
        and len(risk_year_improvement) >= 5
        and risk_mae < unconditional_risk_mae
        and (unconditional_risk_mae - risk_mae)
        / unconditional_risk_mae
        >= 0.005
        and risk_asset_share >= 0.60
        and risk_positive_oos_share >= 0.60
        and risk_positive_year_share >= 0.80
        and risk_bootstrap_probability >= 0.90
    )
    published_assets = scenario_assets if current_phase_publishable else []
    return {
        "status": (
            "blocked_current_phase_disagreement"
            if not current_phase_publishable
            else "passed_vs_hard_phase_only"
            if passed_vs_hard
            else "research_only"
        ),
        "assetForecastStatus": (
            "limited"
            if current_phase_publishable and beats_unconditional
            else "blocked"
        ),
        "riskForecastStatus": (
            "limited"
            if current_phase_publishable and risk_passed
            else "blocked"
        ),
        "asOfPeriod": current_probability["asOfPeriod"],
        "phaseProbabilities": phase_probabilities,
        "primaryPhase": current_probability["primaryPhase"],
        "assets": published_assets,
        "summary": {
            "assets": len(published_assets),
            "validatedAssets": len(validated_assets),
            "assetsBeatingHardPhase": sum(
                bool(row["beatsHardPhase"]) for row in validated_assets
            ),
            "assetsBeatingUnconditional": sum(
                bool(row["beatsUnconditional"]) for row in validated_assets
            ),
            "positiveOosR2": sum(
                float(row["oosR2VsUnconditional"] or 0.0) > 0.0
                for row in validated_assets
            ),
            "assetsBeatingUnconditionalRisk": sum(
                bool(row["beatsUnconditional"])
                for row in risk_asset_validation
            ),
            "positiveRiskOosR2": sum(
                bool(row["positiveOosR2"])
                for row in risk_asset_validation
            ),
            "riskValidatedAssets": len(risk_asset_validation),
        },
        "validation": {
            "observations": int(len(validation_frame)),
            "probabilityMae": _json_value(probability_mae),
            "hardPhaseMae": _json_value(hard_mae),
            "unconditionalMae": _json_value(unconditional_mae),
            "maeImprovementVsHardPhase": _json_value(
                (hard_mae - probability_mae) / hard_mae
            ),
            "maeImprovementVsUnconditional": _json_value(
                (unconditional_mae - probability_mae) / unconditional_mae
            ),
            "assetShareBeatingHardPhase": _json_value(share_beating_hard),
            "assetShareBeatingUnconditional": _json_value(
                share_beating_unconditional
            ),
            "positiveOosR2Share": _json_value(positive_oos_share),
            "risk": {
                "target": "annual_squared_return",
                "phaseWeight": risk_phase_weight,
                "weightCandidates": list(ASSET_RISK_WEIGHT_GRID),
                "weightSelection": {
                    "status": risk_weight_selection["status"],
                    "endYear": risk_weight_selection["endYear"],
                    "observations": risk_weight_selection["observations"],
                    "cycleObservations": risk_weight_selection.get(
                        "cycleObservations", {cycle_id: risk_weight_selection["observations"]}
                    ),
                    "nearBestRelativeTolerance": ASSET_RISK_WEIGHT_MAE_RELATIVE_TOLERANCE,
                    "tieBreak": "smallest_weight_within_tolerance",
                    "maeByWeight": {
                        str(weight): _json_value(error)
                        for weight, error in risk_weight_selection["maeByWeight"].items()
                    },
                },
                "holdout": {
                    "startYear": int(risk_holdout["year"].min()),
                    "endYear": int(risk_holdout["year"].max()),
                    "years": int(len(risk_year_improvement)),
                    "assets": int(len(risk_asset_validation)),
                    "observations": int(len(risk_holdout)),
                    "assetUniverse": "Ken French 48行业和25规模价值组合；JST/FRED CPI实际收益",
                    "weightSensitivity": holdout_weight_sensitivity,
                },
                "riskMae": _json_value(risk_mae),
                "unconditionalRiskMae": _json_value(
                    unconditional_risk_mae
                ),
                "maeImprovementVsUnconditional": _json_value(
                    (unconditional_risk_mae - risk_mae)
                    / unconditional_risk_mae
                ),
                "assetShareBeatingUnconditional": _json_value(
                    risk_asset_share
                ),
                "positiveOosR2Share": _json_value(
                    risk_positive_oos_share
                ),
                "positiveYearShare": _json_value(
                    risk_positive_year_share
                ),
                "yearBlockBootstrapProbability": _json_value(
                    risk_bootstrap_probability
                ),
                "gate": {
                    "minimumHoldoutYears": 5,
                    "minimumHoldoutAssets": 70,
                    "minimumMaeImprovementVsUnconditional": 0.005,
                    "minimumAssetShareBeatingUnconditional": 0.60,
                    "minimumPositiveOosR2Share": 0.60,
                    "minimumPositiveYearShare": 0.80,
                    "minimumYearBlockBootstrapProbability": 0.90,
                },
            },
            "gate": {
                "minimumAssetShareBeatingHardPhase": 0.75,
                "minimumAssetShareBeatingUnconditional": 0.50,
                "minimumPositiveOosR2Share": 0.50,
            },
        },
        "riskDefinition": "C2/C3共用权重仅在2010—2020联合开发样本的0%/10%/25%保守网格中选择，冻结后再用2021—2025 Ken French资产独立留出段验证年度平方收益；不按周期或资产调参。",
        "caveat": (
            "当前只确认地产周期处于低位，住房、信用和投资动量仍分歧；四相位概率及其资产收益风险图暂停发布，历史相位统计继续保留。"
            if not current_phase_publishable
            else (
            "C2平方收益风险挑战者通过有限门槛，但收益层仍未整体战胜无条件基准；只能称为条件风险研究，不称为资产收益预测。"
            if risk_passed
            else "概率混合相对硬相位映射更稳，但收益和平方收益风险均未整体通过门槛，因此只发布历史条件风险收益情景。"
            )
        ),
    }


def build_current_phase_candidate(
    jst: pd.DataFrame,
    cycle_id: str,
    *,
    spp: pd.DataFrame,
    total_credit: pd.DataFrame,
    world_bank: pd.DataFrame,
    oecd_gfcf: pd.DataFrame,
    oecd_house_prices: pd.DataFrame,
) -> dict[str, object]:
    historical_panel = build_macro_only_panel(jst, cycle_id)
    historical_factor, historical_count = _global_factor(historical_panel)

    annual_bridge = build_bridge_panel(
        cycle_id,
        spp=spp,
        total_credit=total_credit,
        world_bank=world_bank,
        oecd_house_prices=oecd_house_prices,
    )
    if cycle_id == "C2":
        partial_panel, partial_metadata = build_c2_partial_year_panel(
            annual_bridge,
            spp,
            oecd_house_prices,
        )
        partial_validation = validate_c2_partial_year_bridge(
            historical_panel,
            annual_bridge,
            spp,
            oecd_house_prices,
        )
    else:
        partial_panel, partial_metadata = build_c3_partial_year_panel(annual_bridge, oecd_gfcf)
        partial_validation = validate_c3_partial_year_bridge(historical_panel, annual_bridge, oecd_gfcf)

    mixed_frequency_validation = validate_mixed_frequency_phase(
        historical_panel,
        annual_bridge,
        cycle_id,
        spp=spp,
        oecd_gfcf=oecd_gfcf,
        oecd_house_prices=oecd_house_prices,
    )

    aligned_annual = _align_bridge_factor(historical_panel, annual_bridge)
    aligned_partial = _align_bridge_factor(historical_panel, partial_panel)
    bridge_factor, bridge_count = _global_factor(aligned_annual)
    overlap = pd.concat(
        {"historical": historical_factor, "bridge": bridge_factor},
        axis=1,
    ).dropna()
    historical_overlap_phase = _adaptive_phase_frame(
        overlap["historical"],
        historical_count.reindex(overlap.index),
        cycle_id=cycle_id,
    ).set_index("year")
    bridge_overlap_phase = _adaptive_phase_frame(
        overlap["bridge"],
        bridge_count.reindex(overlap.index),
        cycle_id=cycle_id,
    ).set_index("year")
    phase_agreement = float(
        (historical_overlap_phase["phase"] == bridge_overlap_phase["phase"]).mean()
    )
    direction_agreement = float(
        (
            historical_overlap_phase["slopeDirection"]
            == bridge_overlap_phase["slopeDirection"]
        ).mean()
    )
    correlation = float(overlap.corr().iloc[0, 1])
    mae = float((overlap["historical"] - overlap["bridge"]).abs().mean())

    historical_end = int(historical_factor.index.max())
    combined_factor = historical_factor.copy()
    combined_count = historical_count.copy()
    bridge_extension = bridge_factor.loc[bridge_factor.index > historical_end]
    combined_factor = pd.concat([combined_factor, bridge_extension])
    combined_count = pd.concat([combined_count, bridge_count.reindex(bridge_extension.index)])
    current_year = int(str(partial_metadata["asOfPeriod"])[:4])
    latest = aligned_partial.sort_values(["iso", "year"]).groupby("iso", as_index=False).tail(1)
    latest = latest.loc[latest["year"] >= current_year - 1].dropna(subset=["factor"])
    combined_factor.loc[current_year] = float(latest["factor"].median())
    combined_count.loc[current_year] = int(len(latest))
    combined_factor = combined_factor.sort_index()
    combined_count = combined_count.reindex(combined_factor.index)
    combined_phase = _adaptive_phase_frame(
        combined_factor,
        combined_count,
        cycle_id=cycle_id,
    )
    current = combined_phase.iloc[-1].to_dict()
    combined_panel = pd.concat(
        [
            historical_panel.loc[historical_panel["year"] <= historical_end],
            aligned_partial.loc[aligned_partial["year"] > historical_end],
        ],
        ignore_index=True,
        sort=False,
    )
    family_confirmation = _family_phase_confirmation(
        combined_panel,
        cycle_id,
        aggregate_phase=str(current["phase"]),
        aggregate_slope_direction=int(current["slopeDirection"]),
        aggregate_level_direction=int(current["levelDirection"]),
        aggregate_period=float(current["periodYears"]),
        as_of_year=current_year,
    )
    family_ablation = _family_ablation_phase_confirmation(
        historical_panel,
        partial_panel,
        cycle_id,
        aggregate_phase=str(current["phase"]),
        aggregate_level_direction=int(current["levelDirection"]),
        aggregate_slope_direction=int(current["slopeDirection"]),
    )
    broad_state = _governed_broad_state(
        current,
        family_confirmation,
        family_ablation,
    )
    period_robustness = (
        _period_robustness(combined_factor, cycle_id)
        if cycle_id == "C2"
        else None
    )
    reliability = (
        0.18 * phase_agreement
        + 0.12 * direction_agreement
        + 0.12 * float(partial_validation.get("directionAccuracy") or 0.0)
        + 0.18 * float(mixed_frequency_validation.get("phaseAccuracy") or 0.0)
        + 0.08 * float(
            mixed_frequency_validation.get("slopeDirectionAccuracy") or 0.0
        )
        + 0.08 * float(
            family_confirmation.get("aggregatePhaseAgreement") or 0.0
        )
        + 0.08 * float(
            family_confirmation.get("aggregateSlopeAgreement") or 0.0
        )
        + 0.08 * float(family_ablation.get("phaseAgreement") or 0.0)
        + 0.08 * float(family_ablation.get("slopeAgreement") or 0.0)
    )
    current["confidence"] = min(float(current["confidence"]), reliability, 0.75)
    combined_phase.loc[combined_phase.index[-1], "confidence"] = current["confidence"]
    period_identification = _period_identification(
        combined_factor,
        cycle_id,
        current,
        family_confirmation,
        period_robustness,
    )
    passed = (
        len(overlap) >= 20
        and correlation >= 0.60
        and phase_agreement >= 0.55
        and direction_agreement >= 0.65
        and partial_validation.get("status") == "passed_limited"
        and mixed_frequency_validation.get("status") == "passed_limited"
        and int(family_confirmation.get("currentFamilyCount") or 0) >= 3
        and float(family_confirmation.get("aggregatePhaseAgreement") or 0.0) >= 0.50
        and float(family_confirmation.get("aggregateSlopeAgreement") or 0.0) >= 0.50
        and float(family_ablation.get("phaseAgreement") or 0.0) >= 0.40
        and float(family_ablation.get("slopeAgreement") or 0.0) >= 0.50
    )
    exact_phase_passed = passed and (
        cycle_id != "C2" or broad_state["momentum"] != "mixed"
    )
    recent = combined_phase.loc[combined_phase["year"] >= historical_end - 2].copy()
    return {
        "status": (
            "limited_current_phase_candidate"
            if exact_phase_passed
            else "limited_broad_state_only"
            if broad_state["status"] == "limited_broad_state"
            else "blocked"
        ),
        "exactPhaseStatus": "limited" if exact_phase_passed else "blocked",
        "formalStatus": "blocked",
        "asOfPeriod": partial_metadata["asOfPeriod"],
        "current": {key: _json_value(value) for key, value in current.items()},
        "factorArchitecture": (
            {
                "definition": "地产—信用核心与宏观传播分层系统",
                "cycleCore": ["住房动量", "按揭信用脉冲"],
                "confirmation": ["投资脉冲", "融资条件变化"],
                "propagation": ["GDP", "消费", "就业", "实际工资", "人口需求"],
                "structuralPosition": ["房价估值", "按揭杠杆", "投资水平"],
                "modelRule": "默认方向模型只使用住房动量与按揭信用；确认层只有在固定目标样本外Brier稳定改善后才允许获得非零权重。",
                "propagationRule": "经济传播层用于验证地产外溢，不反向定义周期；当前虽略改善Brier，但降低方向准确率与国家留一稳定性。",
                "separationRule": "周期相位只由变化型核心通道决定；慢变量只描述结构位置，避免趋势被误识别为超长地产周期。",
            }
            if cycle_id == "C2"
            else None
        ),
        "structuralPosition": _c2_structural_position(jst)
        if cycle_id == "C2"
        else None,
        "governedBroadState": broad_state,
        "periodRobustness": period_robustness,
        "periodIdentification": period_identification,
        "recentHistory": _records(recent),
        "validation": {
            "overlapStart": int(overlap.index.min()),
            "overlapEnd": int(overlap.index.max()),
            "overlapObservations": int(len(overlap)),
            "correlation": _json_value(correlation),
            "mae": _json_value(mae),
            "phaseAgreement": _json_value(phase_agreement),
            "directionAgreement": _json_value(direction_agreement),
            "partialBridge": partial_validation,
            "mixedFrequencyPhase": mixed_frequency_validation,
            "familyConfirmation": family_confirmation,
            "familyAblationPhase": family_ablation,
            "gate": {
                "minimumOverlap": 20,
                "minimumCorrelation": 0.60,
                "minimumPhaseAgreement": 0.55,
                "minimumDirectionAgreement": 0.65,
                "mixedFrequencyPhaseRequired": "passed_limited",
                "minimumCurrentFamilies": 3,
                "minimumFamilyPhaseAgreement": 0.50,
                "minimumFamilySlopeAgreement": 0.50,
                "minimumFamilyAblationPhaseAgreement": 0.40,
                "minimumFamilyAblationSlopeAgreement": 0.50,
            },
        },
        "sourceIdentity": {
            "historical": "JST住房动量—按揭信用核心因子 + 因果自适应趋势周期状态空间",
            "annualBridge": "BIS真实房价/家庭信用 + OECD房价租金比 + World Bank投资确认层",
            "partialBridge": partial_metadata["reason"],
        },
        "caveat": (
            "当前可发布的是高低位宽状态和因子未来方向概率。指标家族动量分歧时，四相位、精确相位角、精确周期长度、拐点和当前资产情景全部阻断。"
            if broad_state["momentum"] == "mixed"
            else "这是跨源一致性、部分年度因子截点和Q1混频四相位截点共同通过后的动态相位候选；周期长度允许随历史证据变化，但原始数据不是真实发布vintage，精确相位角和拐点仍不正式发布。"
        ),
    }


def _parse_ff_monthly(path: Path, section_title: str) -> pd.DataFrame:
    with zipfile.ZipFile(path) as archive:
        member = archive.namelist()[0]
        text = archive.read(member).decode("utf-8", errors="replace")
    lines = text.splitlines()
    title_index = next(index for index, line in enumerate(lines) if section_title in line)
    header_index = title_index + 1
    while header_index < len(lines) and not lines[header_index].startswith(","):
        header_index += 1
    end_index = header_index + 1
    while end_index < len(lines) and lines[end_index].strip():
        end_index += 1
    frame = pd.read_csv(StringIO("\n".join(lines[header_index:end_index])))
    date_column = frame.columns[0]
    dates = pd.to_datetime(frame[date_column].astype(str).str.strip(), format="%Y%m", errors="coerce")
    frame = frame.drop(columns=[date_column])
    frame.index = dates + pd.offsets.MonthEnd(0)
    frame = frame.apply(pd.to_numeric, errors="coerce")
    frame = frame.mask(frame <= -99.0) / 100.0
    return frame.loc[frame.index.notna()].sort_index()


def _annual_compound(monthly: pd.DataFrame) -> pd.DataFrame:
    return (1.0 + monthly).groupby(monthly.index.year).prod(min_count=6) - 1.0


def _real_return(nominal: pd.Series, inflation: pd.Series) -> pd.Series:
    joined = pd.concat({"nominal": nominal, "inflation": inflation}, axis=1)
    result = (1.0 + joined["nominal"]) / (1.0 + joined["inflation"]) - 1.0
    return result.where(result.between(-0.95, 3.0))


def _load_fred_us_annual_inflation() -> pd.Series:
    cached_path = PROJECT_ROOT / "data" / "raw" / "web_public" / "fred_CPIAUCSL.csv"
    path = (
        cached_path
        if cached_path.exists() and cached_path.stat().st_size > 1_000
        else _download(FRED_CPI_URL, RAW_DIR / "fred_CPIAUCSL.csv")
    )
    frame = pd.read_csv(path)
    date_column = "observation_date"
    value_columns = [column for column in frame.columns if column != date_column]
    if len(value_columns) != 1:
        raise ValueError("Unexpected FRED CPI shape")
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    values = pd.to_numeric(frame[value_columns[0]], errors="coerce")
    cpi = pd.Series(values.to_numpy(), index=dates).dropna().sort_index()
    return cpi.groupby(cpi.index.year).mean().pct_change()


def build_asset_universe(jst: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    asset_fields = {
        "eq_tr": "跨国股票",
        "housing_tr": "跨国住房",
        "bond_tr": "跨国国债",
        "bill_rate": "跨国短票",
    }
    for _, country in jst.groupby("iso"):
        country = country.sort_values("year").copy()
        country_name = str(country["country"].iloc[0])
        iso = str(country["iso"].iloc[0])
        inflation = pd.to_numeric(country["cpi"], errors="coerce").pct_change()
        inflation.index = country["year"].astype(int)
        for field, category in asset_fields.items():
            nominal = pd.Series(pd.to_numeric(country[field], errors="coerce").to_numpy(), index=inflation.index)
            real = _real_return(nominal, inflation)
            for year, value in real.dropna().items():
                rows.append(
                    {
                        "assetId": f"JST:{iso}:{field}",
                        "category": category,
                        "name": f"{country_name}·{category.removeprefix('跨国')}",
                        "dataIdentity": "direct_historical_series",
                        "source": "JST Macrohistory R6",
                        "iso": iso,
                        "regionId": C2_ISO_REGION[iso],
                        "year": int(year),
                        "return": float(value),
                    }
                )

    usa = jst.loc[jst["iso"] == "USA"].sort_values("year")
    us_inflation = pd.Series(
        pd.to_numeric(usa["cpi"], errors="coerce").pct_change().to_numpy(),
        index=usa["year"].astype(int),
    )
    fred_inflation = _load_fred_us_annual_inflation()
    us_inflation = pd.concat(
        [
            us_inflation,
            fred_inflation.loc[fred_inflation.index > us_inflation.index.max()],
        ]
    ).sort_index()
    ff_specs = {
        "ff48": ("美国48行业组合", "Average Value Weighted Returns -- Monthly"),
        "ff25": ("美国规模价值组合", "Average Value Weighted Returns -- Monthly"),
    }
    for key, (category, section) in ff_specs.items():
        path = _download(FF_URLS[key], RAW_DIR / f"{key}.zip")
        annual = _annual_compound(_parse_ff_monthly(path, section))
        for column in annual.columns:
            real = _real_return(annual[column], us_inflation)
            for year, value in real.dropna().items():
                rows.append(
                    {
                        "assetId": f"KF:{key}:{column}",
                        "category": category,
                        "name": str(column).strip(),
                        "dataIdentity": "official_research_portfolio_proxy",
                        "source": "Kenneth French Data Library + JST/FRED CPI",
                        "iso": "USA",
                        "regionId": C2_ISO_REGION["USA"],
                        "year": int(year),
                        "return": float(value),
                    }
                )
    return pd.DataFrame(rows).sort_values(["assetId", "year"])


def _phase_mean_oos_r2(frame: pd.DataFrame, min_train: int) -> float | None:
    predictions: list[float] = []
    baselines: list[float] = []
    actual: list[float] = []
    ordered = frame.sort_values("year").reset_index(drop=True)
    for index in range(min_train, len(ordered)):
        train = ordered.iloc[:index]
        current = ordered.iloc[index]
        phase_train = train.loc[train["phase"] == current["phase"], "return"]
        prediction = float(phase_train.mean()) if len(phase_train) >= 3 else float(train["return"].mean())
        predictions.append(prediction)
        baselines.append(float(train["return"].mean()))
        actual.append(float(current["return"]))
    if len(actual) < 10:
        return None
    actual_values = np.asarray(actual)
    model_error = float(np.sum((actual_values - np.asarray(predictions)) ** 2))
    baseline_error = float(np.sum((actual_values - np.asarray(baselines)) ** 2))
    return None if baseline_error <= 1e-12 else 1.0 - model_error / baseline_error


def _phase_hac_pvalue(frame: pd.DataFrame) -> float | None:
    dummies = pd.get_dummies(frame["phase"], prefix="phase", drop_first=True, dtype=float)
    if dummies.shape[1] < 2:
        return None
    design = sm.add_constant(dummies, has_constant="add")
    try:
        model = sm.OLS(frame["return"].astype(float), design.astype(float)).fit(
            cov_type="HAC",
            cov_kwds={"maxlags": 3},
        )
        restriction = np.zeros((dummies.shape[1], design.shape[1]))
        restriction[:, 1:] = np.eye(dummies.shape[1])
        return float(model.f_test(restriction).pvalue)
    except Exception:
        return None


def _forward_asset_target(
    frame: pd.DataFrame,
    horizon: int,
    target: str,
) -> pd.Series:
    ordered = frame.sort_values("year")
    returns_by_year = ordered.set_index("year")["return"].astype(float)
    values: dict[int, float] = {}
    for year in ordered["year"].astype(int):
        future = returns_by_year.reindex(range(year + 1, year + horizon + 1))
        if len(future) != horizon or future.isna().any():
            values[year] = float("nan")
        elif target == "return":
            values[year] = float(np.prod(1.0 + future.to_numpy()) - 1.0)
        else:
            values[year] = float(np.sqrt(np.mean(future.to_numpy() ** 2)))
    return ordered["year"].map(values).set_axis(ordered.index)


def _forward_phase_oos_validation(
    frame: pd.DataFrame,
    horizon: int,
    target: str,
    *,
    min_train: int = 30,
    evaluation_start_year: int | None = None,
) -> dict[str, object] | None:
    ordered = frame.sort_values("year").copy()
    ordered["target"] = _forward_asset_target(ordered, horizon, target)
    ordered = ordered.dropna(subset=["target", "phase"])
    predictions: list[float] = []
    baselines: list[float] = []
    actual: list[float] = []
    for _, current in ordered.iterrows():
        if (
            evaluation_start_year is not None
            and int(current["year"]) < evaluation_start_year
        ):
            continue
        training = ordered.loc[ordered["year"] <= int(current["year"]) - horizon]
        if len(training) < min_train:
            continue
        phase_training = training.loc[
            training["phase"] == current["phase"],
            "target",
        ]
        baseline = float(training["target"].mean())
        prediction = (
            float(phase_training.mean())
            if len(phase_training) >= 3
            else baseline
        )
        predictions.append(prediction)
        baselines.append(baseline)
        actual.append(float(current["target"]))
    if len(actual) < 10:
        return None
    actual_array = np.asarray(actual)
    prediction_array = np.asarray(predictions)
    baseline_array = np.asarray(baselines)
    model_error = float(np.sum((actual_array - prediction_array) ** 2))
    baseline_error = float(np.sum((actual_array - baseline_array) ** 2))
    return {
        "observations": len(actual),
        "oosR2": _json_value(
            1.0 - model_error / baseline_error
            if baseline_error > 1e-12
            else None
        ),
        "mae": _json_value(np.mean(np.abs(actual_array - prediction_array))),
        "baselineMae": _json_value(
            np.mean(np.abs(actual_array - baseline_array))
        ),
        "maeWinRate": _json_value(
            np.mean(
                np.abs(actual_array - prediction_array)
                < np.abs(actual_array - baseline_array)
            )
        ),
    }


def _lagged_phase_validation(
    frame: pd.DataFrame,
    horizon: int,
    target: str,
    *,
    candidate_lags: tuple[int, ...] = (0, 1, 2, 3),
    development_end_year: int = 1989,
) -> dict[str, object] | None:
    development_results: list[tuple[int, dict[str, object]]] = []
    for lag in candidate_lags:
        lagged = frame.copy()
        lagged["phase"] = lagged["phase"].shift(lag)
        development = lagged.loc[lagged["year"] <= development_end_year]
        validation = _forward_phase_oos_validation(
            development,
            horizon,
            target,
            min_train=20,
        )
        if validation is not None and validation["oosR2"] is not None:
            development_results.append((lag, validation))
    if not development_results:
        return None
    selected_lag, development = max(
        development_results,
        key=lambda row: float(row[1]["oosR2"]),
    )
    lagged = frame.copy()
    lagged["phase"] = lagged["phase"].shift(selected_lag)
    validation = _forward_phase_oos_validation(
        lagged,
        horizon,
        target,
        evaluation_start_year=development_end_year + 1,
    )
    if validation is None:
        return None
    return {
        **validation,
        "selectedLagYears": selected_lag,
        "developmentEndYear": development_end_year,
        "developmentOosR2": development["oosR2"],
        "lagSelection": "时滞只在开发期选择，随后在完整递归路径中固定，不按最终结果事后挑选。",
    }


def _forward_state_oos_validation(
    frame: pd.DataFrame,
    feature_columns: list[str],
    horizon: int,
    target: str,
    *,
    min_train: int = 30,
    evaluation_start_year: int | None = None,
) -> dict[str, object] | None:
    ordered = frame.sort_values("year").copy()
    ordered["target"] = _forward_asset_target(ordered, horizon, target)
    ordered = ordered.dropna(subset=["target", *feature_columns])
    predictions: list[float] = []
    baselines: list[float] = []
    actual: list[float] = []
    for _, current in ordered.iterrows():
        if (
            evaluation_start_year is not None
            and int(current["year"]) < evaluation_start_year
        ):
            continue
        training = ordered.loc[ordered["year"] <= int(current["year"]) - horizon]
        if len(training) < min_train:
            continue
        model = make_pipeline(StandardScaler(), Ridge(alpha=20.0))
        model.fit(training[feature_columns], training["target"])
        predictions.append(
            float(model.predict(current[feature_columns].to_frame().T)[0])
        )
        baselines.append(float(training["target"].mean()))
        actual.append(float(current["target"]))
    if len(actual) < 10:
        return None
    actual_array = np.asarray(actual)
    prediction_array = np.asarray(predictions)
    baseline_array = np.asarray(baselines)
    model_error = float(np.sum((actual_array - prediction_array) ** 2))
    baseline_error = float(np.sum((actual_array - baseline_array) ** 2))
    return {
        "observations": len(actual),
        "oosR2": _json_value(
            1.0 - model_error / baseline_error
            if baseline_error > 1e-12
            else None
        ),
        "mae": _json_value(np.mean(np.abs(actual_array - prediction_array))),
        "baselineMae": _json_value(np.mean(np.abs(actual_array - baseline_array))),
        "maeWinRate": _json_value(
            np.mean(
                np.abs(actual_array - prediction_array)
                < np.abs(actual_array - baseline_array)
            )
        ),
    }


def build_c2_geographic_asset_validation(
    asset_universe: pd.DataFrame,
    global_phase_history: pd.DataFrame,
    country_phase_history: pd.DataFrame,
    region_phase_history: pd.DataFrame,
    *,
    eligible_asset_ids: set[str],
) -> dict[str, object]:
    global_state = global_phase_history[["year", "phase", "value"]].rename(
        columns={"phase": "globalPhase", "value": "globalValue"}
    )
    country_value_column = (
        "activity" if "activity" in country_phase_history else "value"
    )
    region_value_column = (
        "activity" if "activity" in region_phase_history else "value"
    )
    country_state = country_phase_history[
        ["iso", "year", "phase", country_value_column]
    ].rename(
        columns={
            "phase": "countryPhase",
            country_value_column: "countryValue",
        }
    )
    region_state = region_phase_history[
        ["regionId", "year", "phase", region_value_column]
    ].rename(
        columns={
            "phase": "regionPhase",
            region_value_column: "regionValue",
        }
    )
    joined = (
        asset_universe.loc[asset_universe["assetId"].isin(eligible_asset_ids)]
        .merge(global_state, on="year", how="inner")
        .merge(region_state, on=["regionId", "year"], how="inner")
        .merge(country_state, on=["iso", "year"], how="inner")
    )
    joined["regionDeviation"] = joined["regionValue"] - joined["globalValue"]
    joined["countryDeviation"] = joined["countryValue"] - joined["regionValue"]
    joined["countryDeviationLag1"] = joined.groupby("assetId")[
        "countryDeviation"
    ].shift(1)
    joined["countryDeviationLag2"] = joined.groupby("assetId")[
        "countryDeviation"
    ].shift(2)
    joined["countryDeviationLag3"] = joined.groupby("assetId")[
        "countryDeviation"
    ].shift(3)
    model_columns = {
        "global": ("全球C2", "globalPhase"),
        "region": ("区域C2", "regionPhase"),
        "country": ("本国C2", "countryPhase"),
        "countryLagged": ("本国C2·固定时滞", "countryPhase"),
        "decomposition": ("共同项+区域/本国偏离", "globalPhase"),
    }
    asset_results: list[dict[str, object]] = []
    cell_rows: dict[str, list[dict[str, object]]] = {
        cell_id: [] for cell_id in C2_GEOGRAPHIC_VALIDATION_CELLS
    }
    for asset_id, asset in joined.groupby("assetId"):
        first = asset.iloc[0]
        cells: dict[str, object] = {}
        for cell_id, (horizon, target, _) in C2_GEOGRAPHIC_VALIDATION_CELLS.items():
            common = asset[
                [
                    "year",
                    "return",
                    "globalPhase",
                    "regionPhase",
                    "countryPhase",
                    "globalValue",
                    "regionDeviation",
                    "countryDeviation",
                    "countryDeviationLag1",
                    "countryDeviationLag2",
                    "countryDeviationLag3",
                ]
            ].dropna()
            models: dict[str, object] = {}
            for model_id, (_, phase_column) in model_columns.items():
                frame = common[["year", "return", phase_column]].rename(
                    columns={phase_column: "phase"}
                )
                validation = (
                    _forward_state_oos_validation(
                        common,
                        [
                            "globalValue",
                            "regionDeviation",
                            "countryDeviation",
                            "countryDeviationLag1",
                            "countryDeviationLag2",
                            "countryDeviationLag3",
                        ],
                        horizon,
                        target,
                        evaluation_start_year=1990,
                    )
                    if model_id == "decomposition"
                    else _lagged_phase_validation(frame, horizon, target)
                    if model_id == "countryLagged"
                    else _forward_phase_oos_validation(
                        frame,
                        horizon,
                        target,
                        evaluation_start_year=1990,
                    )
                )
                if validation is not None:
                    models[model_id] = validation
            if set(models) != set(model_columns):
                continue
            cells[cell_id] = models
            for model_id, validation in models.items():
                cell_rows[cell_id].append(
                    {
                        "assetId": str(asset_id),
                        "category": str(first["category"]),
                        "modelId": model_id,
                        "oosR2": validation["oosR2"],
                        "mae": validation["mae"],
                        "baselineMae": validation["baselineMae"],
                    }
                )
        if cells:
            asset_results.append(
                {
                    "assetId": str(asset_id),
                    "category": str(first["category"]),
                    "name": str(first["name"]),
                    "iso": str(first["iso"]),
                    "regionId": str(first["regionId"]),
                    "cells": cells,
                }
            )

    cell_summaries: dict[str, object] = {}
    candidate_passes: dict[str, list[bool]] = {
        "region": [],
        "country": [],
        "countryLagged": [],
        "decomposition": [],
    }
    relative_cells: list[dict[str, object]] = []
    for cell_id, (_, _, label) in C2_GEOGRAPHIC_VALIDATION_CELLS.items():
        rows = pd.DataFrame(cell_rows[cell_id])
        model_summaries: dict[str, object] = {}
        global_rows = rows.loc[rows["modelId"] == "global"].set_index("assetId")
        for model_id, (model_label, _) in model_columns.items():
            model_rows = rows.loc[rows["modelId"] == model_id].set_index("assetId")
            oos_values = pd.to_numeric(model_rows["oosR2"], errors="coerce").dropna()
            mae_values = pd.to_numeric(model_rows["mae"], errors="coerce").dropna()
            summary: dict[str, object] = {
                "label": model_label,
                "assets": int(len(oos_values)),
                "positiveOosR2": int((oos_values > 0).sum()),
                "positiveOosR2Share": _json_value((oos_values > 0).mean()),
                "medianOosR2": _json_value(oos_values.median()),
                "medianMae": _json_value(mae_values.median()),
            }
            if model_id != "global":
                common_ids = model_rows.index.intersection(global_rows.index)
                model_common = model_rows.loc[common_ids]
                global_common = global_rows.loc[common_ids]
                model_r2 = pd.to_numeric(model_common["oosR2"], errors="coerce")
                global_r2 = pd.to_numeric(global_common["oosR2"], errors="coerce")
                model_mae = pd.to_numeric(model_common["mae"], errors="coerce")
                global_mae = pd.to_numeric(global_common["mae"], errors="coerce")
                comparison = {
                    "assets": int(len(common_ids)),
                    "shareBeatingGlobalOosR2": _json_value(
                        (model_r2 > global_r2).mean()
                    ),
                    "shareBeatingGlobalMae": _json_value(
                        (model_mae < global_mae).mean()
                    ),
                    "medianOosR2Delta": _json_value(
                        (model_r2 - global_r2).median()
                    ),
                }
                passed = (
                    len(oos_values) >= C2_GEOGRAPHIC_MINIMUM_ASSETS
                    and float((oos_values > 0).mean()) >= 0.50
                    and float(oos_values.median()) >= 0.0
                    and float(comparison["shareBeatingGlobalOosR2"] or 0.0)
                    >= 0.60
                    and float(comparison["shareBeatingGlobalMae"] or 0.0)
                    >= 0.60
                )
                comparison["passed"] = passed
                summary["comparisonVsGlobal"] = comparison
                candidate_passes[model_id].append(passed)
                relative_cells.append(
                    {
                        "modelId": model_id,
                        "cellId": cell_id,
                        "label": label,
                        "medianOosR2Delta": comparison["medianOosR2Delta"],
                    }
                )
            model_summaries[model_id] = summary
        cell_summaries[cell_id] = {
            "label": label,
            "models": model_summaries,
        }

    candidates = []
    for model_id in ("region", "country", "countryLagged", "decomposition"):
        passed_cells = sum(candidate_passes[model_id])
        candidates.append(
            {
                "modelId": model_id,
                "label": model_columns[model_id][0],
                "passedCells": passed_cells,
                "cellCount": len(C2_GEOGRAPHIC_VALIDATION_CELLS),
                "passed": passed_cells == len(C2_GEOGRAPHIC_VALIDATION_CELLS),
            }
        )
    strongest_relative_cell = max(
        relative_cells,
        key=lambda row: float(row["medianOosR2Delta"] or -np.inf),
    )
    return {
        "status": "passed_limited"
        if any(candidate["passed"] for candidate in candidates)
        else "failed",
        "lookAhead": False,
        "commonEligibleAssets": int(len(asset_results)),
        "cells": cell_summaries,
        "candidates": candidates,
        "strongestRelativeCell": strongest_relative_cell,
        "assetResults": asset_results,
        "gate": {
            "minimumAssets": C2_GEOGRAPHIC_MINIMUM_ASSETS,
            "minimumPositiveOosR2Share": 0.50,
            "minimumMedianOosR2": 0.0,
            "minimumShareBeatingGlobalOosR2": 0.60,
            "minimumShareBeatingGlobalMae": 0.60,
            "allFourReturnRiskCellsMustPass": True,
        },
        "method": "同一资产、同一年份和同一递归截点，比较全球、区域、本国和固定时滞本国C2；时滞只在1989年前开发期选择，随后固定验证，避免事后挑选。训练集只纳入当时已完全兑现的未来结果。",
        "conclusion": "国家错位已进入资产验证，但只有固定时滞模型在收益、风险和1/3年四个单元均取得绝对样本外改善，才允许替代全球C2。当前门槛未通过，仍不解锁资产预测。",
        "caveat": "相对全球模型更好不等于具有可用预测力；只有绝对样本外R²、误差胜率和跨收益风险期限同时通过，才允许进入资产映射。",
    }


def build_asset_mapping(
    asset_universe: pd.DataFrame,
    phase_history: pd.DataFrame,
    cycle_id: str,
) -> dict[str, object]:
    joined = asset_universe.merge(phase_history[["year", "phase", "value", "slope"]], on="year", how="inner")
    min_observations = 50 if cycle_id == "C2" else 40
    min_phase_count = 6
    assets: list[dict[str, object]] = []
    for asset_id, frame in joined.groupby("assetId"):
        frame = frame.dropna(subset=["return", "phase"]).sort_values("year")
        if frame.empty:
            continue
        first = frame.iloc[0]
        self_referential = (
            cycle_id == "C2"
            and str(first["category"]) == "跨国住房"
        )
        phase_stats: dict[str, object] = {}
        phase_means: dict[str, float] = {}
        phase_counts: list[int] = []
        for phase in PHASE_LABELS:
            returns = frame.loc[frame["phase"] == phase, "return"].astype(float)
            phase_counts.append(len(returns))
            phase_means[phase] = float(returns.mean()) if len(returns) else float("nan")
            phase_stats[phase] = {
                "n": len(returns),
                "annReturn": _json_value(returns.mean() if len(returns) else None),
                "annVol": _json_value(returns.std(ddof=1) if len(returns) > 1 else None),
                "medianReturn": _json_value(returns.median() if len(returns) else None),
                "positiveRate": _json_value((returns > 0).mean() if len(returns) else None),
            }
        valid_means = {phase: value for phase, value in phase_means.items() if np.isfinite(value)}
        best_phase = max(valid_means, key=valid_means.get) if valid_means else None
        worst_phase = min(valid_means, key=valid_means.get) if valid_means else None
        spread = valid_means[best_phase] - valid_means[worst_phase] if best_phase and worst_phase else None
        eligible = (
            not self_referential
            and len(frame) >= min_observations
            and min(phase_counts) >= min_phase_count
        )
        oos_r2 = _phase_mean_oos_r2(frame, min_train=30 if cycle_id == "C2" else 25) if eligible else None
        p_value = _phase_hac_pvalue(frame) if eligible else None
        forward_validation = None
        if eligible and cycle_id == "C2":
            forward_validation = {
                "1yReturn": _forward_phase_oos_validation(frame, 1, "return"),
                "3yReturn": _forward_phase_oos_validation(frame, 3, "return"),
                "1yRisk": _forward_phase_oos_validation(frame, 1, "risk"),
                "3yRisk": _forward_phase_oos_validation(frame, 3, "risk"),
            }
        if eligible and len(frame) >= 80 and min(phase_counts) >= 10 and (oos_r2 or -1.0) > 0 and (p_value or 1.0) < 0.10:
            confidence = "high"
        elif eligible and ((oos_r2 or -1.0) > 0 or (p_value or 1.0) < 0.20):
            confidence = "medium"
        else:
            confidence = "low"
        assets.append(
            {
                "assetId": asset_id,
                "category": first["category"],
                "name": first["name"],
                "dataIdentity": first["dataIdentity"],
                "source": first["source"],
                "iso": first["iso"],
                "regionId": first["regionId"],
                "startYear": int(frame["year"].min()),
                "endYear": int(frame["year"].max()),
                "observations": int(len(frame)),
                "eligible": eligible,
                "phaseStats": phase_stats,
                "bestPhase": best_phase,
                "worstPhase": worst_phase,
                "phaseSpread": _json_value(spread),
                "oosR2": _json_value(oos_r2),
                "hacPValue": _json_value(p_value),
                "forwardValidation": forward_validation,
                "confidence": confidence,
                "exclusionReason": (
                    "C2核心含住房价格动量，跨国住房收益会形成自解释，故不进入可用资产映射。"
                    if self_referential
                    else None
                ),
                "caveat": (
                    "C2核心含住房价格动量，跨国住房收益仅保留原始统计，不进入可用映射。"
                    if self_referential
                    else "历史相位条件关联，不是因果归因或投资建议。"
                ),
            }
        )
    eligible_assets = [asset for asset in assets if asset["eligible"]]
    eligible_p_values = np.asarray(
        [
            float(asset["hacPValue"])
            if asset["hacPValue"] is not None
            else 1.0
            for asset in eligible_assets
        ],
        dtype="float64",
    )
    if len(eligible_p_values):
        rejected, adjusted, _, _ = multipletests(
            eligible_p_values,
            alpha=0.10,
            method="fdr_bh",
        )
        for asset, passed, adjusted_p in zip(
            eligible_assets,
            rejected,
            adjusted,
            strict=True,
        ):
            asset["hacFdrQValue"] = _json_value(adjusted_p)
            asset["hacFdrPassed"] = bool(passed)
            if cycle_id == "C2":
                forward = asset.get("forwardValidation") or {}
                forward_return_positive = [
                    float((forward.get(key) or {}).get("oosR2") or 0.0) > 0.0
                    for key in ("1yReturn", "3yReturn")
                ]
                if (
                    passed
                    and float(asset.get("oosR2") or 0.0) > 0.0
                    and all(forward_return_positive)
                ):
                    asset["confidence"] = "high"
                elif (
                    float(asset.get("oosR2") or 0.0) > 0.0
                    and any(forward_return_positive)
                ):
                    asset["confidence"] = "medium"
                else:
                    asset["confidence"] = "low"
    forward_summary = None
    if cycle_id == "C2":
        forward_summary = {}
        for validation_id in ("1yReturn", "3yReturn", "1yRisk", "3yRisk"):
            rows = [
                asset["forwardValidation"][validation_id]
                for asset in eligible_assets
                if asset.get("forwardValidation")
                and asset["forwardValidation"].get(validation_id)
            ]
            oos_values = [
                float(row["oosR2"])
                for row in rows
                if row["oosR2"] is not None
            ]
            forward_summary[validation_id] = {
                "assets": len(rows),
                "positiveOosR2": sum(value > 0 for value in oos_values),
                "positiveOosR2Share": _json_value(
                    np.mean(np.asarray(oos_values) > 0) if oos_values else None
                ),
                "medianOosR2": _json_value(
                    np.median(oos_values) if oos_values else None
                ),
                "assetsWithMaeWinRateAboveHalf": sum(
                    float(row["maeWinRate"] or 0.0) > 0.50 for row in rows
                ),
            }
        forward_summary["gate"] = {
            "minimumPositiveOosR2Share": 0.50,
            "minimumMedianOosR2": 0.0,
            "allReturnAndRiskHorizonsMustPass": True,
        }
        forward_summary["status"] = (
            "passed_limited"
            if all(
                float(forward_summary[validation_id]["positiveOosR2Share"] or 0.0)
                >= 0.50
                and float(forward_summary[validation_id]["medianOosR2"] or -1.0)
                >= 0.0
                for validation_id in ("1yReturn", "3yReturn", "1yRisk", "3yRisk")
            )
            else "failed"
        )
        forward_summary["method"] = (
            "当年C2相位预测未来1年和3年的累计实际收益与均方收益风险；"
            "每个截点训练集只使用当时已经完整兑现的未来结果，避免期限重叠造成前视。"
        )
    return {
        "status": "research_mapping_candidate",
        "summary": {
            "totalAssets": len(assets),
            "eligibleAssets": len(eligible_assets),
            "highConfidence": sum(asset["confidence"] == "high" for asset in eligible_assets),
            "mediumConfidence": sum(asset["confidence"] == "medium" for asset in eligible_assets),
            "positiveOosR2": sum((asset["oosR2"] or 0.0) > 0 for asset in eligible_assets),
            "hacFdrPassed": sum(bool(asset.get("hacFdrPassed")) for asset in eligible_assets),
            "forwardValidation": forward_summary,
            "categories": sorted({str(asset["category"]) for asset in assets}),
        },
        "assets": assets,
        "method": {
            "factor": "周期因子不含资产总收益；C2另将跨国住房收益标记为自解释并排除出可用资产映射。",
            "returns": "年度实际收益；JST直接历史序列与Ken French官方研究组合分开标识。",
            "validation": "同期统计使用扩展窗口相位均值和HAC；C2另用严格递归截点检验未来1/3年收益与风险，并对多资产HAC结果做Benjamini-Hochberg FDR校正。",
            "multipleTesting": "121条可用C2资产同时检验采用10% FDR；未经校正的单个p值不作为稳定映射依据。",
            "minimumSample": f"{min_observations}年且每个相位至少{min_phase_count}个观测。",
        },
    }


def build_payload() -> dict[str, object]:
    jst = _load_jst()
    spp, total_credit = _fetch_bis()
    world_bank = _fetch_world_bank()
    oecd_gfcf = _fetch_oecd_gfcf()
    oecd_house_prices = _fetch_oecd_house_prices()
    asset_universe = build_asset_universe(jst)
    cycles: dict[str, object] = {}
    phase_histories: dict[str, pd.DataFrame] = {}
    for cycle_id in ("C2", "C3"):
        phase_history = build_phase_history(jst, cycle_id)
        phase_histories[cycle_id] = phase_history
        validation = phase_validation(jst, phase_history, cycle_id)
        phase_counts = phase_history["phase"].value_counts().to_dict()
        current_phase_candidate = build_current_phase_candidate(
            jst,
            cycle_id,
            spp=spp,
            total_credit=total_credit,
            world_bank=world_bank,
            oecd_gfcf=oecd_gfcf,
            oecd_house_prices=oecd_house_prices,
        )
        asset_mapping = build_asset_mapping(asset_universe, phase_history, cycle_id)
        cycles[cycle_id] = {
            "cycleId": cycle_id,
            "status": "adaptive_phase_candidate",
            "formalStatus": "blocked",
            "history": _records(phase_history),
            "turns": _turns(phase_history, cycle_id),
            "phaseCounts": {phase: int(phase_counts.get(phase, 0)) for phase in PHASE_LABELS},
            "validation": validation,
            "currentPhaseCandidate": current_phase_candidate,
            "assetMapping": asset_mapping,
            "caveat": "历史相位使用因果宏观因子与动态趋势-周期状态空间分解，可作为研究划分；原始数据真实vintage、精确拐点和因果资产归因仍未达到正式门槛。",
        }
        if cycle_id == "C2":
            historical_panel = build_macro_only_panel(jst, "C2")
            country_phase_history, region_phase_history = (
                _c2_geographic_phase_frames(historical_panel)
            )
            cycles[cycle_id]["geographicState"] = build_c2_geographic_state(
                jst,
                spp=spp,
                total_credit=total_credit,
                world_bank=world_bank,
                oecd_house_prices=oecd_house_prices,
                global_candidate=current_phase_candidate,
            )
            eligible_asset_ids = {
                str(asset["assetId"])
                for asset in asset_mapping["assets"]
                if asset["eligible"]
            }
            asset_mapping["geographicValidation"] = (
                build_c2_geographic_asset_validation(
                    asset_universe,
                    phase_history,
                    country_phase_history,
                    region_phase_history,
                    eligible_asset_ids=eligible_asset_ids,
                )
            )
            asset_mapping["interactionValidation"] = {
                "status": "not_run_geographic_gate_failed",
                "preregisteredCandidates": [
                    "C2 × 估值",
                    "C2 × 实际利率",
                    "C2 × 信用条件",
                ],
                "reason": "国家级和区域级C2尚未先通过绝对资产预测门槛；按预注册顺序停止后续交互搜索，避免在失败结果上继续挑变量。",
            }
    phase_probability_calibration = build_phase_probability_calibration(cycles)
    prepared_scenarios = {
        cycle_id: _prepare_probability_weighted_asset_scenario(
            asset_universe,
            phase_histories[cycle_id],
            cycles[cycle_id]["assetMapping"],
            phase_probability_calibration,
            cycle_id,
            cycles[cycle_id]["currentPhaseCandidate"],
        )
        for cycle_id in ("C2", "C3")
    }
    risk_weight_selection = _select_shared_asset_risk_weight(prepared_scenarios)
    for cycle_id in ("C2", "C3"):
        cycles[cycle_id]["assetMapping"]["currentProbabilityWeightedScenario"] = (
            build_probability_weighted_asset_scenario(
                asset_universe,
                phase_histories[cycle_id],
                cycles[cycle_id]["assetMapping"],
                phase_probability_calibration,
                cycle_id,
                cycles[cycle_id]["currentPhaseCandidate"],
                prepared=prepared_scenarios[cycle_id],
                risk_weight_selection=risk_weight_selection,
            )
        )
    return {
        "meta": {
            "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
            "phaseLabels": PHASE_LABELS,
            "assetUniverse": "JST 18国股票/住房/国债/短票 + Ken French 48行业和25规模价值组合",
            "attributionLabel": "objective historical phase association; not causal attribution",
        },
        "cycles": cycles,
        "phaseProbabilityCalibration": phase_probability_calibration,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUTPUT_PATH}")
    for cycle_id, cycle in payload["cycles"].items():
        print(
            cycle_id,
            "history=",
            len(cycle["history"]),
            "eligible_assets=",
            cycle["assetMapping"]["summary"]["eligibleAssets"],
            "positive_oos=",
            cycle["assetMapping"]["summary"]["positiveOosR2"],
        )


if __name__ == "__main__":
    main()
