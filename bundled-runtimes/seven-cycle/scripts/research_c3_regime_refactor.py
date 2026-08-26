"""Build the independent C3 capital-cycle research model."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from seven_cycle_platform.cycles import adaptive_harmonic_state_filter

try:
    from scripts.research_c2_c3_long_panel import (
        JST_COUNTRIES,
        _fetch_bis,
        _fetch_oecd_gfcf,
        _fetch_world_bank,
        _load_jst,
        build_bridge_panel,
        build_c3_partial_year_panel,
        causal_robust_z,
    )
except ModuleNotFoundError:
    from research_c2_c3_long_panel import (  # type: ignore[no-redef]
        JST_COUNTRIES,
        _fetch_bis,
        _fetch_oecd_gfcf,
        _fetch_world_bank,
        _load_jst,
        build_bridge_panel,
        build_c3_partial_year_panel,
        causal_robust_z,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output" / "c3_regime_refactor.json"
MODEL_VERSION = "c3-dual-core-v1"

CORE_FAMILIES = (
    "investment_impulse3",
    "business_credit_impulse3",
)
CONFIRMATION_FAMILIES = (
    "real_gdp_growth3",
    "financing_easing3",
)
STRUCTURAL_FAMILIES = ("investment_position",)
FORBIDDEN_INPUTS = (
    "equity_return3",
    "bond_return",
    "commodity_return",
    "housing_return",
)
ARCHITECTURES = {
    "investment_single": {
        "label": "固定投资脉冲单因子",
        "modelFamilies": ("investment_impulse3",),
    },
    "business_credit_single": {
        "label": "企业信用脉冲单因子",
        "modelFamilies": ("business_credit_impulse3",),
    },
    "dual_core": {
        "label": "投资脉冲 + 企业信用双核心",
        "modelFamilies": CORE_FAMILIES,
    },
    "dual_core_macro_confirmation": {
        "label": "双核心 + GDP/融资确认",
        "modelFamilies": (*CORE_FAMILIES, *CONFIRMATION_FAMILIES),
    },
}
PHASE_LABELS = {
    "recovery": "复苏",
    "expansion": "扩张",
    "slowdown": "放缓",
    "contraction": "收缩",
}
PHASE_SEARCH_BANDS = ((5.0, 14.0), (5.0, 18.0), (6.0, 16.0))
PRIMARY_SEARCH_BAND = PHASE_SEARCH_BANDS[1]
C3_PRIOR_YEARS = 100.0 / 12.0
DIRECTION_HORIZONS = (1, 2, 3)
ASSET_HORIZONS = (1, 3)


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
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


def _safe_auc(actual: np.ndarray, probabilities: np.ndarray) -> float | None:
    if len(actual) == 0 or len(np.unique(actual)) < 2:
        return None
    return float(roc_auc_score(actual, probabilities))


def _classifier(*, regularization: float = 0.1) -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        LogisticRegression(
            C=regularization,
            max_iter=1_000,
            class_weight="balanced",
        ),
    )


def _country_features(country: pd.DataFrame) -> pd.DataFrame:
    country = country.sort_values("year").set_index("year")
    nominal_gdp = pd.to_numeric(country["gdp"], errors="coerce").where(
        lambda value: value > 0
    )
    prices = pd.to_numeric(country["cpi"], errors="coerce").where(
        lambda value: value > 0
    )
    real_gdp = pd.to_numeric(country["rgdpmad"], errors="coerce").where(
        lambda value: value > 0
    )
    investment_share = pd.to_numeric(country["iy"], errors="coerce")
    business_credit_share = (
        pd.to_numeric(country["tbus"], errors="coerce") / nominal_gdp
    )
    inflation = np.log(prices).diff()
    real_short_rate = (
        pd.to_numeric(country["stir"], errors="coerce") / 100.0 - inflation
    )
    return pd.DataFrame(
        {
            "investment_impulse3": causal_robust_z(
                investment_share.diff(3) / 3.0
            ),
            "business_credit_impulse3": causal_robust_z(
                business_credit_share.diff(3) / 3.0
            ),
            "real_gdp_growth3": causal_robust_z(
                np.log(real_gdp).diff(3) / 3.0
            ),
            "financing_easing3": causal_robust_z(
                -real_short_rate.diff(3) / 3.0
            ),
            "investment_position": causal_robust_z(investment_share),
        },
        index=country.index,
    )


def _rebuild_core_factor(
    panel: pd.DataFrame,
    *,
    smoothing_span: int = 3,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    core_columns = [f"family_{family}" for family in CORE_FAMILIES]
    for _, country in panel.groupby("iso"):
        country = country.sort_values("year").copy()
        core = country[core_columns]
        country["factor"] = (
            core.mean(axis=1, skipna=True)
            .where(core.notna().sum(axis=1) == len(core_columns))
            .ewm(span=smoothing_span, adjust=False, min_periods=2)
            .mean()
        )
        rows.append(country)
    return pd.concat(rows, ignore_index=True)


def build_historical_panel(
    jst: pd.DataFrame,
    *,
    smoothing_span: int = 3,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for iso, country in jst.groupby("iso"):
        features = _country_features(country).add_prefix("family_")
        features["iso"] = iso
        features["year"] = features.index.astype(int)
        rows.append(features.reset_index(drop=True))
    panel = pd.concat(rows, ignore_index=True)
    return _rebuild_core_factor(panel, smoothing_span=smoothing_span)


def _world_bank_financing_features(world_bank: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for iso, country in world_bank.groupby("iso"):
        country = country.sort_values("year").set_index("year")
        real_lending_rate = (
            pd.to_numeric(country["lending_rate"], errors="coerce")
            - pd.to_numeric(country["cpi_inflation"], errors="coerce")
        ) / 100.0
        rows.append(
            pd.DataFrame(
                {
                    "iso": iso,
                    "year": country.index.astype(int),
                    "family_financing_easing3": causal_robust_z(
                        -real_lending_rate.diff(3) / 3.0,
                        window=20,
                        min_periods=10,
                    ),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _align_bridge_columns(
    historical: pd.DataFrame,
    bridge: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "factor",
        *[
            f"family_{family}"
            for family in (*CORE_FAMILIES, *CONFIRMATION_FAMILIES)
        ],
    ]
    aligned: list[pd.DataFrame] = []
    for iso, country in bridge.groupby("iso"):
        country = country.sort_values("year").copy()
        history = historical.loc[historical["iso"] == iso]
        for column in columns:
            if column not in country or column not in history:
                continue
            overlap = country[["year", column]].merge(
                history[["year", column]],
                on="year",
                suffixes=("Bridge", "Historical"),
            ).dropna()
            if len(overlap) < 10:
                continue
            bridge_std = float(overlap[f"{column}Bridge"].std(ddof=0))
            historical_std = float(overlap[f"{column}Historical"].std(ddof=0))
            if bridge_std <= 1e-8 or historical_std <= 1e-8:
                continue
            country[column] = (
                (
                    country[column]
                    - float(overlap[f"{column}Bridge"].mean())
                )
                / bridge_std
                * historical_std
                + float(overlap[f"{column}Historical"].mean())
            )
        aligned.append(country)
    return pd.concat(aligned, ignore_index=True)


def build_current_bridge(
    historical: pd.DataFrame,
    *,
    spp: pd.DataFrame,
    total_credit: pd.DataFrame,
    world_bank: pd.DataFrame,
    oecd_gfcf: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    annual = build_bridge_panel(
        "C3",
        spp=spp,
        total_credit=total_credit,
        world_bank=world_bank,
    ).drop(columns=["factor"], errors="ignore")
    annual = annual.merge(
        _world_bank_financing_features(world_bank),
        on=["iso", "year"],
        how="left",
    )
    annual["family_investment_position"] = annual.get(
        "family_investment_share"
    )
    annual = annual.drop(columns=["family_investment_share"], errors="ignore")
    annual = _rebuild_core_factor(annual)
    partial, metadata = build_c3_partial_year_panel(annual, oecd_gfcf)
    partial = _rebuild_core_factor(partial.drop(columns=["factor"], errors="ignore"))
    return (
        _align_bridge_columns(historical, annual),
        _align_bridge_columns(historical, partial),
        metadata,
    )


def _global_factor(panel: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    pivot = panel.pivot_table(
        index="year",
        columns="iso",
        values="factor",
        aggfunc="last",
    )
    country_count = pivot.notna().sum(axis=1)
    factor = pivot.median(axis=1, skipna=True).where(country_count >= 6).dropna()
    return factor, country_count.reindex(factor.index).astype(int)


def _persistent_sign(series: pd.Series, deadband: pd.Series) -> pd.Series:
    state = 0
    values: list[int] = []
    for value, threshold in zip(series, deadband.reindex(series.index), strict=True):
        if not np.isfinite(value):
            values.append(state)
            continue
        bounded = float(threshold) if np.isfinite(threshold) else 0.0
        if value > bounded:
            state = 1
        elif value < -bounded:
            state = -1
        elif state == 0:
            state = 1 if value >= 0 else -1
        values.append(state)
    return pd.Series(values, index=series.index, dtype="int64")


def _phase_name(level: int, slope: int) -> str:
    if level < 0 and slope >= 0:
        return "recovery"
    if level >= 0 and slope >= 0:
        return "expansion"
    if level >= 0:
        return "slowdown"
    return "contraction"


def build_phase_history(
    factor: pd.Series,
    country_count: pd.Series,
    *,
    search_band: tuple[float, float] = PRIMARY_SEARCH_BAND,
) -> pd.DataFrame:
    state = adaptive_harmonic_state_filter(
        factor,
        period_min=search_band[0],
        period_max=search_band[1],
        period_step=0.25,
        score_window=80,
        min_score_observations=40,
        period_prior=C3_PRIOR_YEARS,
        period_prior_weight=0.01,
    )
    level_scale = state.level.expanding(min_periods=20).std(ddof=0).shift(1)
    slope_scale = state.slope.expanding(min_periods=20).std(ddof=0).shift(1)
    level_sign = _persistent_sign(
        state.level,
        (level_scale * 0.08).clip(lower=0.015).fillna(0.0),
    )
    slope_sign = _persistent_sign(
        state.slope,
        (slope_scale * 0.08).clip(lower=0.004).fillna(0.0),
    )
    phase = [
        _phase_name(int(level_sign.loc[year]), int(slope_sign.loc[year]))
        for year in factor.index
    ]
    return pd.DataFrame(
        {
            "year": factor.index.astype(int),
            "rawValue": factor.to_numpy(),
            "trend": state.trend.to_numpy(),
            "value": state.level.to_numpy(),
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
            "phase": phase,
            "countryCount": country_count.reindex(factor.index).to_numpy(),
        }
    )


def build_parameter_robustness(
    factor: pd.Series,
    country_count: pd.Series,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for search_band in PHASE_SEARCH_BANDS:
        current = build_phase_history(
            factor,
            country_count,
            search_band=search_band,
        ).iloc[-1]
        rows.append(
            {
                "searchBandYears": list(search_band),
                "phase": str(current["phase"]),
                "levelDirection": int(current["levelDirection"]),
                "slopeDirection": int(current["slopeDirection"]),
                "periodYears": _json_value(current["periodYears"]),
                "periodBoundaryShare": _json_value(
                    current["periodBoundaryShare"]
                ),
            }
        )
    periods = np.asarray([float(row["periodYears"]) for row in rows])
    primary_phase = rows[1]["phase"]
    return {
        "status": "stable_band" if len(set(periods.round(2))) <= 2 else "sensitive",
        "phaseAgreement": _json_value(
            np.mean([row["phase"] == primary_phase for row in rows])
        ),
        "levelDirectionAgreement": _json_value(
            np.mean(
                [
                    row["levelDirection"] == rows[1]["levelDirection"]
                    for row in rows
                ]
            )
        ),
        "slopeDirectionAgreement": _json_value(
            np.mean(
                [
                    row["slopeDirection"] == rows[1]["slopeDirection"]
                    for row in rows
                ]
            )
        ),
        "periodRangeYears": [
            _json_value(periods.min()),
            _json_value(periods.max()),
        ],
        "boundaryFreeShare": _json_value(
            np.mean([float(row["periodBoundaryShare"]) == 0.0 for row in rows])
        ),
        "specifications": rows,
        "method": "100个月仅以1%惩罚强度进入先验；5—18年内的候选周期仍由滚动预测似然选择。",
    }


def _model_frame(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for _, country in panel.groupby("iso"):
        country = country.sort_values("year").copy()
        for lag in range(1, 7):
            country[f"coreLag{lag}"] = country["factor"].shift(lag)
        country["coreSlope1"] = country["factor"].diff()
        country["coreSlope3"] = country["factor"].diff(3) / 3.0
        country["coreSlope5"] = country["factor"].diff(5) / 5.0
        country["futureCore"] = country["factor"].shift(-horizon)
        country["targetUp"] = (
            country["futureCore"] > country["factor"]
        ).astype(float)
        rows.append(country)
    return pd.concat(rows, ignore_index=True).dropna(
        subset=["factor", "futureCore", "targetUp", "coreSlope3"]
    )


BASE_DIRECTION_COLUMNS = (
    "coreLag1",
    "coreLag2",
    "coreLag3",
    "coreLag4",
    "coreLag5",
    "coreLag6",
    "coreSlope1",
    "coreSlope3",
    "coreSlope5",
)


def _recursive_direction_predictions(
    panel: pd.DataFrame,
    *,
    horizon: int,
    model_families: tuple[str, ...],
    regularization: float = 0.1,
) -> pd.DataFrame:
    frame = _model_frame(panel, horizon)
    family_columns = [f"family_{family}" for family in model_families]
    candidate_columns = [*BASE_DIRECTION_COLUMNS, *family_columns]
    rows: list[pd.DataFrame] = []
    for year in sorted(frame["year"].unique()):
        if year < 1950:
            continue
        train = frame.loc[frame["year"] <= year - horizon]
        test = frame.loc[frame["year"] == year]
        if len(train) < 250 or test.empty or train["targetUp"].nunique() < 2:
            continue
        baseline = _classifier(regularization=regularization)
        candidate = _classifier(regularization=regularization)
        target = train["targetUp"].astype(int)
        baseline.fit(train[list(BASE_DIRECTION_COLUMNS)], target)
        candidate.fit(train[candidate_columns], target)
        result = test[["iso", "year", "targetUp"]].copy()
        result["baselineProbability"] = baseline.predict_proba(
            test[list(BASE_DIRECTION_COLUMNS)]
        )[:, 1]
        result["candidateProbability"] = candidate.predict_proba(
            test[candidate_columns]
        )[:, 1]
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


def _prediction_metrics(predictions: pd.DataFrame) -> dict[str, object]:
    actual = predictions["targetUp"].astype(int).to_numpy()
    baseline = predictions["baselineProbability"].to_numpy()
    candidate = predictions["candidateProbability"].to_numpy()
    baseline_auc = _safe_auc(actual, baseline)
    candidate_auc = _safe_auc(actual, candidate)
    country_accuracy = (
        predictions.assign(
            correct=(predictions["candidateProbability"] >= 0.5)
            == predictions["targetUp"].astype(int)
        )
        .groupby("iso")["correct"]
        .mean()
    )
    return {
        "observations": int(len(predictions)),
        "accuracy": _json_value(np.mean((candidate >= 0.5) == actual)),
        "baselineAccuracy": _json_value(np.mean((baseline >= 0.5) == actual)),
        "auc": _json_value(candidate_auc),
        "baselineAuc": _json_value(baseline_auc),
        "aucImprovement": _json_value(
            None
            if candidate_auc is None or baseline_auc is None
            else candidate_auc - baseline_auc
        ),
        "brier": _json_value(brier_score_loss(actual, candidate)),
        "baselineBrier": _json_value(brier_score_loss(actual, baseline)),
        "brierImprovement": _json_value(
            brier_score_loss(actual, baseline)
            - brier_score_loss(actual, candidate)
        ),
        "countryMedianAccuracy": _json_value(country_accuracy.median()),
    }


def _leave_country_out_direction(
    panel: pd.DataFrame,
    *,
    horizon: int,
    model_families: tuple[str, ...],
) -> dict[str, object]:
    frame = _model_frame(panel, horizon)
    family_columns = [f"family_{family}" for family in model_families]
    candidate_columns = [*BASE_DIRECTION_COLUMNS, *family_columns]
    rows: list[pd.DataFrame] = []
    for iso in sorted(frame["iso"].unique()):
        train = frame.loc[(frame["iso"] != iso) & (frame["year"] <= 1999)]
        test = frame.loc[(frame["iso"] == iso) & (frame["year"] >= 2000)]
        if len(train) < 250 or test.empty or train["targetUp"].nunique() < 2:
            continue
        baseline = _classifier()
        candidate = _classifier()
        target = train["targetUp"].astype(int)
        baseline.fit(train[list(BASE_DIRECTION_COLUMNS)], target)
        candidate.fit(train[candidate_columns], target)
        result = test[["iso", "year", "targetUp"]].copy()
        result["baselineProbability"] = baseline.predict_proba(
            test[list(BASE_DIRECTION_COLUMNS)]
        )[:, 1]
        result["candidateProbability"] = candidate.predict_proba(
            test[candidate_columns]
        )[:, 1]
        rows.append(result)
    predictions = pd.concat(rows, ignore_index=True)
    return _prediction_metrics(predictions)


def _validate_architecture(
    panel: pd.DataFrame,
    architecture_id: str,
) -> dict[str, object]:
    architecture = ARCHITECTURES[architecture_id]
    model_families = tuple(architecture["modelFamilies"])
    horizons: dict[str, object] = {}
    passes: list[bool] = []
    for horizon in DIRECTION_HORIZONS:
        predictions = _recursive_direction_predictions(
            panel,
            horizon=horizon,
            model_families=model_families,
        )
        metrics = _prediction_metrics(predictions)
        subperiods = []
        for start, end in ((1950, 1984), (1985, 2020)):
            period = predictions.loc[predictions["year"].between(start, end)]
            period_metrics = _prediction_metrics(period)
            period_metrics.update({"start": start, "end": end})
            subperiods.append(period_metrics)
        leave_country = _leave_country_out_direction(
            panel,
            horizon=horizon,
            model_families=model_families,
        )
        passed = (
            metrics["observations"] >= 800
            and float(metrics["auc"] or 0.0) >= 0.60
            and float(metrics["aucImprovement"] or 0.0) >= 0.01
            and float(metrics["brierImprovement"] or 0.0) >= 0.002
            and all(
                float(period["brierImprovement"] or -1.0) >= 0.0
                for period in subperiods
            )
            and float(leave_country["brierImprovement"] or -1.0) >= 0.0
        )
        metrics["subperiods"] = subperiods
        metrics["leaveCountryOut2000Plus"] = leave_country
        metrics["passed"] = passed
        horizons[f"{horizon}y"] = metrics
        passes.append(passed)
    regularization = {}
    for value in (0.05, 0.1, 0.2):
        prediction = _recursive_direction_predictions(
            panel,
            horizon=1,
            model_families=model_families,
            regularization=value,
        )
        metrics = _prediction_metrics(prediction)
        regularization[str(value)] = {
            "aucImprovement": metrics["aucImprovement"],
            "brierImprovement": metrics["brierImprovement"],
        }
    return {
        "architectureId": architecture_id,
        "label": architecture["label"],
        "modelFamilies": list(model_families),
        "commonTarget": "未来投资脉冲—企业信用双核心因子的方向",
        "passedHorizons": sum(passes),
        "horizonCount": len(passes),
        "passed": all(passes),
        "horizons": horizons,
        "regularizationPlateau": regularization,
    }


def build_architecture_comparison(panel: pd.DataFrame) -> dict[str, object]:
    architectures = [
        _validate_architecture(panel, architecture_id)
        for architecture_id in ARCHITECTURES
    ]
    dual = next(
        row for row in architectures if row["architectureId"] == "dual_core"
    )
    layered = next(
        row
        for row in architectures
        if row["architectureId"] == "dual_core_macro_confirmation"
    )
    confirmation_brier_delta = np.mean(
        [
            float(layered["horizons"][f"{horizon}y"]["brier"])
            - float(dual["horizons"][f"{horizon}y"]["brier"])
            for horizon in DIRECTION_HORIZONS
        ]
    )
    confirmation_promoted = (
        confirmation_brier_delta < 0.0
        and all(
            float(
                layered["horizons"][f"{horizon}y"]["brierImprovement"]
                or 0.0
            )
            >= float(
                dual["horizons"][f"{horizon}y"]["brierImprovement"]
                or 0.0
            )
            for horizon in DIRECTION_HORIZONS
        )
    )
    return {
        "status": (
            "dual_core_with_confirmation_selected"
            if confirmation_promoted
            else "dual_core_selected_confirmation_not_promoted"
        ),
        "selectedArchitecture": (
            "dual_core_macro_confirmation"
            if confirmation_promoted
            else "dual_core"
        ),
        "architectures": architectures,
        "confirmationPromoted": confirmation_promoted,
        "confirmationMeanBrierDeltaVsDualCore": _json_value(
            confirmation_brier_delta
        ),
        "conclusion": (
            "GDP与融资确认在全部期限稳定改善双核心模型。"
            if confirmation_promoted
            else "高方向准确率主要来自双核心自身惯性；GDP与融资确认未在前后时期和国家留一中形成稳定增量。"
        ),
        "governance": {
            "targetFixedAcrossArchitectures": True,
            "assetPriceInputsExcluded": True,
            "forbiddenInputs": list(FORBIDDEN_INPUTS),
            "selectionRule": "双核心按经济定义预注册；确认层只有在1/2/3年递归样本外、前后时期和国家留一同时改善时才升级。",
        },
    }


def _current_direction_forecast(
    historical: pd.DataFrame,
    current_panel: pd.DataFrame,
    *,
    horizon: int,
    model_families: tuple[str, ...],
    as_of_period: str,
) -> dict[str, object]:
    historical_model = _model_frame(historical, horizon)
    family_columns = [f"family_{family}" for family in model_families]
    feature_columns = [*BASE_DIRECTION_COLUMNS, *family_columns]
    model = _classifier()
    model.fit(
        historical_model[feature_columns],
        historical_model["targetUp"].astype(int),
    )
    rows: list[pd.DataFrame] = []
    for _, country in current_panel.groupby("iso"):
        country = country.sort_values("year").copy()
        for lag in range(1, 7):
            country[f"coreLag{lag}"] = country["factor"].shift(lag)
        country["coreSlope1"] = country["factor"].diff()
        country["coreSlope3"] = country["factor"].diff(3) / 3.0
        country["coreSlope5"] = country["factor"].diff(5) / 5.0
        eligible = country.dropna(subset=["factor", "coreSlope3"])
        if not eligible.empty:
            rows.append(eligible.tail(1))
    current = pd.concat(rows, ignore_index=True)
    for column in feature_columns:
        if column not in current:
            current[column] = np.nan
    current["probabilityUp"] = model.predict_proba(current[feature_columns])[:, 1]
    latest_year = int(current["year"].max())
    latest = current.loc[current["year"] >= latest_year - 1].copy()
    probability = float(latest["probabilityUp"].mean())
    current_factor = float(latest["factor"].median())
    historical_change = (
        historical_model["futureCore"] - historical_model["factor"]
    )
    expected_change = (
        (2.0 * probability - 1.0)
        * float(historical_change.abs().median())
    )
    return {
        "asOfYear": latest_year,
        "asOfPeriod": as_of_period,
        "horizonYears": horizon,
        "probabilityUp": _json_value(probability),
        "probabilityDown": _json_value(1.0 - probability),
        "direction": (
            "上行概率占优"
            if probability >= 0.55
            else "下行概率占优"
            if probability <= 0.45
            else "方向接近均衡"
        ),
        "countryCount": int(len(latest)),
        "currentFactor": _json_value(current_factor),
        "scenarioFactor": _json_value(current_factor + expected_change),
        "scenarioLow": _json_value(
            current_factor + historical_change.quantile(0.20)
        ),
        "scenarioHigh": _json_value(
            current_factor + historical_change.quantile(0.80)
        ),
    }


def _asset_panel(jst: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    fields = {
        "eq_tr": "跨国股票",
        "bond_tr": "跨国国债",
    }
    for iso, country in jst.groupby("iso"):
        country = country.sort_values("year")
        inflation = pd.to_numeric(country["cpi"], errors="coerce").pct_change()
        for field, category in fields.items():
            nominal = pd.to_numeric(country[field], errors="coerce")
            real = (1.0 + nominal) / (1.0 + inflation) - 1.0
            for year, value in zip(country["year"], real, strict=True):
                if np.isfinite(value) and -0.95 < value < 3.0:
                    rows.append(
                        {
                            "iso": iso,
                            "year": int(year),
                            "category": category,
                            "return": float(value),
                        }
                    )
    return pd.DataFrame(rows)


def _forward_asset_frame(
    assets: pd.DataFrame,
    *,
    horizon: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for (_, category), asset in assets.groupby(["iso", "category"]):
        asset = asset.sort_values("year").copy()
        values = asset["return"].to_numpy(dtype="float64")
        forward_return: list[float] = []
        forward_risk: list[float] = []
        for position in range(len(asset)):
            path = values[position + 1 : position + 1 + horizon]
            if len(path) < horizon or not np.isfinite(path).all():
                forward_return.append(np.nan)
                forward_risk.append(np.nan)
                continue
            forward_return.append(float(np.prod(1.0 + path) - 1.0))
            if category == "跨国股票":
                curve = np.concatenate(([1.0], np.cumprod(1.0 + path)))
                peak = np.maximum.accumulate(curve)
                forward_risk.append(float(np.max(1.0 - curve / peak)))
            else:
                forward_risk.append(
                    float(np.sqrt(np.mean(np.minimum(path, 0.0) ** 2)))
                )
        asset["assetReturn"] = asset["return"]
        asset["assetMomentum3"] = asset["return"].rolling(3, min_periods=2).mean()
        asset["assetRisk3"] = asset["return"].rolling(3, min_periods=2).std(ddof=0)
        asset["forwardReturn"] = forward_return
        asset["forwardRisk"] = forward_risk
        rows.append(asset)
    return pd.concat(rows, ignore_index=True)


def _asset_metrics(predictions: pd.DataFrame) -> dict[str, object]:
    actual = predictions["actual"].astype(int).to_numpy()
    baseline = predictions["baselineProbability"].to_numpy()
    candidate = predictions["candidateProbability"].to_numpy()
    baseline_auc = _safe_auc(actual, baseline)
    candidate_auc = _safe_auc(actual, candidate)
    return {
        "observations": int(len(predictions)),
        "accuracy": _json_value(np.mean((candidate >= 0.5) == actual)),
        "baselineAccuracy": _json_value(np.mean((baseline >= 0.5) == actual)),
        "auc": _json_value(candidate_auc),
        "baselineAuc": _json_value(baseline_auc),
        "aucImprovement": _json_value(
            None
            if candidate_auc is None or baseline_auc is None
            else candidate_auc - baseline_auc
        ),
        "brier": _json_value(brier_score_loss(actual, candidate)),
        "baselineBrier": _json_value(brier_score_loss(actual, baseline)),
        "brierImprovement": _json_value(
            brier_score_loss(actual, baseline)
            - brier_score_loss(actual, candidate)
        ),
    }


def _asset_predictions(
    frame: pd.DataFrame,
    *,
    horizon: int,
    target: str,
) -> pd.DataFrame:
    baseline_columns = ["assetReturn", "assetMomentum3", "assetRisk3"]
    c3_columns = ["factor", "c3Slope1", "c3Slope3"]
    rows: list[pd.DataFrame] = []
    for year in sorted(frame["year"].unique()):
        if year < 1950:
            continue
        train = frame.loc[frame["year"] <= year - horizon].copy()
        test = frame.loc[frame["year"] == year].copy()
        if len(train) < 250 or test.empty:
            continue
        if target == "return":
            train["actual"] = (train["forwardReturn"] > 0.0).astype(int)
            test["actual"] = (test["forwardReturn"] > 0.0).astype(int)
        else:
            global_threshold = float(train["forwardRisk"].quantile(0.75))
            country_threshold = train.groupby("iso")["forwardRisk"].agg(
                count="count",
                threshold=lambda values: values.quantile(0.75),
            )
            valid_threshold = country_threshold.loc[
                country_threshold["count"] >= 20,
                "threshold",
            ].to_dict()
            train_threshold = train["iso"].map(valid_threshold).fillna(
                global_threshold
            )
            test_threshold = test["iso"].map(valid_threshold).fillna(
                global_threshold
            )
            train["actual"] = (
                train["forwardRisk"] > train_threshold
            ).astype(int)
            test["actual"] = (
                test["forwardRisk"] > test_threshold
            ).astype(int)
        if train["actual"].nunique() < 2:
            continue
        baseline = _classifier()
        candidate = _classifier()
        baseline.fit(train[baseline_columns], train["actual"])
        candidate.fit(train[[*baseline_columns, *c3_columns]], train["actual"])
        result = test[["iso", "year", "actual"]].copy()
        result["baselineProbability"] = baseline.predict_proba(
            test[baseline_columns]
        )[:, 1]
        result["candidateProbability"] = candidate.predict_proba(
            test[[*baseline_columns, *c3_columns]]
        )[:, 1]
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


def build_asset_validation(
    jst: pd.DataFrame,
    historical: pd.DataFrame,
) -> dict[str, object]:
    c3 = historical[["iso", "year", "factor"]].copy()
    c3["c3Slope1"] = c3.groupby("iso")["factor"].diff()
    c3["c3Slope3"] = c3.groupby("iso")["factor"].diff(3) / 3.0
    assets = _asset_panel(jst)
    cells: list[dict[str, object]] = []
    for category in ("跨国股票", "跨国国债"):
        for horizon in ASSET_HORIZONS:
            target_frame = _forward_asset_frame(
                assets.loc[assets["category"] == category],
                horizon=horizon,
            ).merge(c3, on=["iso", "year"], how="inner").dropna()
            for target in ("return", "risk"):
                predictions = _asset_predictions(
                    target_frame,
                    horizon=horizon,
                    target=target,
                )
                metrics = _asset_metrics(predictions)
                subperiods = []
                for start, end in ((1950, 1984), (1985, 2020)):
                    period = predictions.loc[
                        predictions["year"].between(start, end)
                    ]
                    period_metrics = _asset_metrics(period)
                    period_metrics.update({"start": start, "end": end})
                    subperiods.append(period_metrics)
                passed = (
                    metrics["observations"] >= 350
                    and float(metrics["auc"] or 0.0) >= 0.55
                    and float(metrics["aucImprovement"] or 0.0) >= 0.01
                    and float(metrics["brierImprovement"] or 0.0) >= 0.001
                    and all(
                        float(period["brierImprovement"] or -1.0) >= 0.0
                        for period in subperiods
                    )
                )
                cells.append(
                    {
                        "category": category,
                        "horizonYears": horizon,
                        "target": target,
                        "targetLabel": (
                            "实际累计收益方向"
                            if target == "return"
                            else "最大回撤高风险"
                            if category == "跨国股票"
                            else "下行损失高风险"
                        ),
                        **metrics,
                        "subperiods": subperiods,
                        "passed": passed,
                    }
                )
    passed_cells = sum(bool(cell["passed"]) for cell in cells)
    return {
        "status": "passed_limited" if passed_cells >= 6 else "failed",
        "passedTargets": passed_cells,
        "targetCount": len(cells),
        "cells": cells,
        "commodityValidation": {
            "status": "not_run_missing_reliable_long_panel",
            "reason": "Ken French Gold/Oil 是行业股票，不是商品现货；现有黄金、原油、铜直接价格历史不足以覆盖多个C3周期。",
        },
        "gate": {
            "minimumPassedTargets": 6,
            "minimumAuc": 0.55,
            "minimumAucImprovement": 0.01,
            "minimumBrierImprovement": 0.001,
            "bothSubperiodsMustNotDegrade": True,
        },
        "method": "股票和国债分开检验未来1/3年实际收益方向与风险；基准只含资产自身收益、动量和波动，挑战者增加本国C3水平与斜率。",
        "caveat": "这是单周期增量信息检验，不是组合回测、因果归因或配置建议。",
    }


def build_payload(*, refresh: bool = False) -> dict[str, object]:
    jst = _load_jst(refresh=refresh)
    spp, total_credit = _fetch_bis(refresh=refresh)
    world_bank = _fetch_world_bank(refresh=refresh)
    oecd_gfcf = _fetch_oecd_gfcf(refresh=refresh)
    historical = build_historical_panel(jst)
    annual_bridge, partial_bridge, partial_metadata = build_current_bridge(
        historical,
        spp=spp,
        total_credit=total_credit,
        world_bank=world_bank,
        oecd_gfcf=oecd_gfcf,
    )
    historical_factor, historical_count = _global_factor(historical)
    partial_factor, partial_count = _global_factor(partial_bridge)
    historical_end = int(historical_factor.index.max())
    extension = partial_factor.loc[partial_factor.index > historical_end]
    combined_factor = pd.concat([historical_factor, extension]).sort_index()
    combined_count = pd.concat(
        [historical_count, partial_count.reindex(extension.index)]
    ).reindex(combined_factor.index)
    phase_history = build_phase_history(combined_factor, combined_count)
    current = phase_history.iloc[-1]
    robustness = build_parameter_robustness(combined_factor, combined_count)
    architecture = build_architecture_comparison(historical)
    selected_families = tuple(
        ARCHITECTURES[architecture["selectedArchitecture"]]["modelFamilies"]
    )
    forecasts = [
        _current_direction_forecast(
            historical,
            partial_bridge,
            horizon=horizon,
            model_families=selected_families,
            as_of_period=str(partial_metadata["asOfPeriod"]),
        )
        for horizon in DIRECTION_HORIZONS
    ]
    asset_validation = build_asset_validation(jst, historical)
    point = {
        "date": partial_metadata["plotDate"],
        "label": partial_metadata["asOfPeriod"],
        "value": _json_value(extension.iloc[-1]),
        "countryCount": int(partial_count.loc[extension.index[-1]]),
        "updatedCountryCount": int(partial_metadata["countryCount"]),
    }
    return {
        "meta": {
            "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
            "modelVersion": MODEL_VERSION,
            "asOfPeriod": partial_metadata["asOfPeriod"],
            "historicalCoverage": "JST 18国，1870—2020，年度",
            "currentBridge": "BIS企业信用 + World Bank投资/GDP/融资 + OECD季度实际固定资本形成",
        },
        "factorArchitecture": {
            "definition": "资本形成双核心与宏观确认分层系统",
            "cycleCore": ["固定投资脉冲", "企业信用脉冲"],
            "confirmation": ["实际GDP", "实际融资条件"],
            "structuralPosition": ["投资占GDP比重"],
            "excludedInputs": list(FORBIDDEN_INPUTS),
            "missingModernConfirmations": ["企业利润率长历史", "产能利用率长历史"],
        },
        "state": {
            "status": "limited_dynamic_state",
            "history": _records(phase_history),
            "current": {
                key: _json_value(current[key])
                for key in (
                    "year",
                    "rawValue",
                    "value",
                    "slope",
                    "angle",
                    "periodYears",
                    "periodLowYears",
                    "periodHighYears",
                    "phaseAgreement",
                    "periodBoundaryShare",
                    "periodSelectionStrength",
                    "levelDirection",
                    "slopeDirection",
                    "phase",
                    "countryCount",
                )
            },
            "parameterRobustness": robustness,
            "phaseLabels": PHASE_LABELS,
            "prior": {
                "centerMonths": 100,
                "role": "weak_prior_only",
                "penaltyWeight": 0.01,
                "searchBandYears": list(PRIMARY_SEARCH_BAND),
            },
        },
        "architectureComparison": architecture,
        "currentForecasts": forecasts,
        "partialNowcast": {
            **partial_metadata,
            "point": point,
            "annualBridgeHistory": [
                {"date": str(year), "value": _json_value(value)}
                for year, value in _global_factor(annual_bridge)[0].items()
                if year > historical_end
            ],
        },
        "assetValidation": asset_validation,
        "decision": {
            "status": "retain_as_limited_capital_state",
            "assetForecastStatus": "blocked",
            "reason": "双核心可形成稳定动态宽状态，但方向模型对自身惯性的增量有限，资产验证未达到多数通道通过门槛。",
        },
        "governance": {
            "formalStatus": "blocked",
            "publishable": ["资本双核心历史状态", "当前宽状态", "1至3年因子方向概率"],
            "notAllowed": [
                "把100个月当固定正弦波",
                "用股票或商品收益定义C3",
                "把因子方向概率写成资产涨跌概率",
                "输出组合权重或精确拐点",
            ],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    payload = build_payload(refresh=args.refresh)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote: {OUTPUT_PATH}")
    print(
        "phase=",
        payload["state"]["current"]["phase"],
        "period=",
        payload["state"]["current"]["periodYears"],
        "asset_passed=",
        payload["assetValidation"]["passedTargets"],
        "/",
        payload["assetValidation"]["targetCount"],
    )


if __name__ == "__main__":
    main()
