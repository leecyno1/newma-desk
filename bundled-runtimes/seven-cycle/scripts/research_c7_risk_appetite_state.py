"""Build a governed C7 risk-appetite and market-trading state model.

C7 is treated as a fast regime process rather than a fixed six-month sine
wave. The state combines market returns, style preference, turnover,
margin-financing acceleration and dollar safe-haven pressure. Forecast gates
are evaluated separately for one, three and six-month future risk-on regimes.
Asset direction is tested with a non-price subset so that a price-derived
state cannot validate itself through circular mapping.
"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import math
from urllib.request import urlretrieve

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    from scripts.research_c5_liquidity_state import (
        ASSET_GROUPS as C7_ASSET_GROUPS,
        _asset_baseline_features,
        _asset_direction_robust_validation,
        _asset_risk_validation,
        _future_return,
        _future_volatility,
    )
except ModuleNotFoundError:
    from research_c5_liquidity_state import (
        ASSET_GROUPS as C7_ASSET_GROUPS,
        _asset_baseline_features,
        _asset_direction_robust_validation,
        _asset_risk_validation,
        _future_return,
        _future_volatility,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_monthly.parquet"
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json"
PUBLIC_SIGNAL_DIR = PROJECT_ROOT / "data" / "raw" / "web_public"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
FRED_SIGNAL_IDS = ("VIXCLS", "NFCI", "BAA", "AAA")
REGIME_AUC_GATE = 0.68
FORECAST_PATH_HORIZONS = tuple(range(1, 7))
HEADLINE_HORIZONS = (1, 3, 6)

MARKET_RETURN_COLUMNS = [
    "US_FF3_MKT_RF_RET",
    "IDX_SH_COMP_MOM",
    "IDX_SZ_COMP_MOM",
    "IDX_HS300_MOM",
    "IDX_CSI500_MOM",
    "IDX_GEM_MOM",
]

TURNOVER_COLUMNS = [
    "IDX_SH_COMP_TURNOVER_RATE_LEVEL",
    "IDX_SZ_COMP_TURNOVER_RATE_LEVEL",
    "IDX_HS300_TURNOVER_RATE_LEVEL",
    "IDX_CSI500_TURNOVER_RATE_LEVEL",
    "IDX_GEM_TURNOVER_RATE_LEVEL",
]

FAMILY_WEIGHTS = pd.Series(
    {
        "市场收益": 1.0,
        "风格偏好": 1.0,
        "交易活跃": 1.0,
        "融资拥挤": 1.0,
        "外部避险": 1.0,
        "波动信用压力": 1.0,
    }
)

RISK_ASSET_CATEGORIES = {
    "A股宽基指数",
    "海外指数/ETF",
    "申万一级行业",
    "美股行业ETF",
    "风格/规模指数",
    "FF 17行业组合(US)",
}


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m")
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _monthly_panel() -> pd.DataFrame:
    panel = pd.read_parquet(PANEL_PATH)
    panel.index = pd.to_datetime(panel.index)
    panel = panel.groupby(panel.index.to_period("M")).last()
    panel.index = panel.index.to_timestamp("M")
    return panel.sort_index()


def _refresh_public_signals() -> None:
    PUBLIC_SIGNAL_DIR.mkdir(parents=True, exist_ok=True)
    for series_id in FRED_SIGNAL_IDS:
        urlretrieve(
            FRED_URL.format(series_id=series_id),
            PUBLIC_SIGNAL_DIR / f"fred_{series_id}.csv",
        )


def _fred_monthly(series_id: str, *, aggregation: str = "mean") -> pd.Series:
    path = PUBLIC_SIGNAL_DIR / f"fred_{series_id}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path}; run research_c7_risk_appetite_state.py --refresh-public"
        )
    frame = pd.read_csv(path)
    series = pd.to_numeric(frame[series_id], errors="coerce")
    series.index = pd.to_datetime(frame["observation_date"])
    if aggregation == "last":
        return series.resample("ME").last()
    return series.resample("ME").mean()


def _causal_robust_z(
    series: pd.Series,
    *,
    window: int = 60,
    min_periods: int = 24,
) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    rolling = numeric.rolling(window, min_periods=min_periods)
    center = rolling.median()
    mad = (numeric - center).abs().rolling(
        window, min_periods=min_periods
    ).median() * 1.4826
    fallback = rolling.std(ddof=0)
    scale = mad.where(mad > 1e-8, fallback).replace(0, np.nan)
    return ((numeric - center) / scale).clip(-4.0, 4.0)


def _family_mean(series: list[pd.Series]) -> pd.Series:
    return pd.concat(series, axis=1).mean(axis=1, skipna=True)


def build_risk_appetite_state(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    market = _family_mean(
        [_causal_robust_z(panel[column]) for column in MARKET_RETURN_COLUMNS]
    )
    style = _family_mean(
        [
            _causal_robust_z(
                panel["IDX_CSI300_HIGH_BETA_MOM"] - panel["IDX_CSI_DIV_LOWVOL_MOM"]
            ),
            _causal_robust_z(panel["IDX_GEM_MOM"] - panel["IDX_HS300_MOM"]),
            _causal_robust_z(panel["US_FF_MOM_RET"]),
        ]
    )
    activity = _family_mean(
        [
            _causal_robust_z(np.log(panel[column].where(panel[column] > 0)))
            for column in TURNOVER_COLUMNS
        ]
    )
    margin_level = (
        panel["CN_MARGIN_SH_FIN_AK_LEVEL"].fillna(0)
        + panel["CN_MARGIN_SZ_FIN_AK_LEVEL"].fillna(0)
    ).replace(0, np.nan)
    leverage = _causal_robust_z(np.log(margin_level).diff(3) / 3.0)
    refuge = _causal_robust_z(-panel["DXY_MOM"])
    vix = _fred_monthly("VIXCLS")
    financial_conditions = _fred_monthly("NFCI")
    credit_spread = _fred_monthly("BAA") - _fred_monthly("AAA")
    stress = _family_mean(
        [
            _causal_robust_z(-np.log(vix.where(vix > 0))),
            _causal_robust_z(-financial_conditions),
            _causal_robust_z(-credit_spread),
        ]
    )
    families = pd.concat(
        {
            "市场收益": market,
            "风格偏好": style,
            "交易活跃": activity,
            "融资拥挤": leverage,
            "外部避险": refuge,
            "波动信用压力": stress,
        },
        axis=1,
    )
    available_weight = families.notna().mul(FAMILY_WEIGHTS).sum(axis=1)
    weighted_state = families.mul(FAMILY_WEIGHTS).sum(axis=1, min_count=2)
    composite = (weighted_state / available_weight).where(
        families.notna().sum(axis=1) >= 2
    )
    end = composite.last_valid_index()
    if end is None:
        raise RuntimeError("C7 risk-appetite composite unavailable")
    families = families.loc[:end]
    state = composite.loc[:end].ewm(span=3, adjust=False, min_periods=3).mean()
    return families, state


def _feature_frame(families: pd.DataFrame, state: pd.Series) -> pd.DataFrame:
    features = families.copy()
    features["state"] = state
    for lag in range(1, 7):
        features[f"lag_{lag}"] = state.shift(lag)
    features["slope_1"] = state.diff()
    features["slope_3"] = state.diff(3) / 3.0
    features["acceleration"] = features["slope_1"].diff()
    features["family_disagreement"] = families.std(axis=1, ddof=0)
    return features


def _non_price_feature_frame(families: pd.DataFrame) -> pd.DataFrame:
    non_price = families[["交易活跃", "融资拥挤", "外部避险"]]
    features = non_price.copy()
    for column in non_price:
        features[f"{column}_slope_1"] = non_price[column].diff()
        features[f"{column}_slope_3"] = non_price[column].diff(3) / 3.0
        for lag in (1, 2, 3, 6):
            features[f"{column}_lag_{lag}"] = non_price[column].shift(lag)
    return features.shift(1)


def _classifier() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        LogisticRegression(
            C=0.03,
            max_iter=2_000,
            class_weight="balanced",
        ),
    )


def _safe_auc(actual: np.ndarray, probabilities: np.ndarray) -> float | None:
    if len(np.unique(actual)) < 2:
        return None
    return float(roc_auc_score(actual, probabilities))


def _validation_metrics(
    actual: np.ndarray,
    probabilities: np.ndarray,
    base_probabilities: np.ndarray,
    persistence: np.ndarray,
) -> dict[str, object]:
    if len(actual) == 0:
        return {
            "observations": 0,
            "accuracy": None,
            "persistenceAccuracy": None,
            "baseAccuracy": None,
            "brier": None,
            "baseBrier": None,
            "persistenceBrier": None,
            "auc": None,
        }
    return {
        "observations": int(len(actual)),
        "accuracy": _json_value(np.mean((probabilities >= 0.5) == actual)),
        "persistenceAccuracy": _json_value(np.mean(persistence == actual)),
        "baseAccuracy": _json_value(np.mean((base_probabilities >= 0.5) == actual)),
        "brier": _json_value(brier_score_loss(actual, probabilities)),
        "baseBrier": _json_value(brier_score_loss(actual, base_probabilities)),
        "persistenceBrier": _json_value(
            brier_score_loss(actual, persistence.astype(float))
        ),
        "auc": _json_value(_safe_auc(actual, probabilities)),
    }


def validate_regime_probability(
    families: pd.DataFrame,
    state: pd.Series,
    horizon: int,
) -> tuple[dict[str, object], dict[str, object]]:
    features = _feature_frame(families, state)
    future_state = state.shift(-horizon)
    target = (future_state > 0).astype(float).where(future_state.notna())
    frame = (
        features.join(target.rename("target_risk_on"))
        .join(future_state.rename("future_state"))
        .dropna(subset=["state", "slope_3", "target_risk_on", "future_state"])
    )
    feature_columns = list(features.columns)
    probabilities: list[float] = []
    base_probabilities: list[float] = []
    actual: list[int] = []
    persistence: list[int] = []
    dates: list[pd.Timestamp] = []
    for current_date in frame.index:
        train = frame.loc[frame.index <= current_date - pd.DateOffset(months=horizon)]
        test = frame.loc[[current_date]]
        if len(train) < 72 or train["target_risk_on"].nunique() < 2:
            continue
        eligible_columns = [
            column
            for column in feature_columns
            if train[column].notna().any() and test[column].notna().any()
        ]
        model = _classifier()
        model.fit(train[eligible_columns], train["target_risk_on"].astype(int))
        probabilities.append(
            float(model.predict_proba(test[eligible_columns])[:, 1][0])
        )
        base_probabilities.append(float(train["target_risk_on"].mean()))
        actual.append(int(test["target_risk_on"].iloc[0]))
        persistence.append(int(test["state"].iloc[0] > 0))
        dates.append(pd.Timestamp(current_date))

    probability_array = np.asarray(probabilities)
    base_array = np.asarray(base_probabilities)
    actual_array = np.asarray(actual)
    persistence_array = np.asarray(persistence)
    result = _validation_metrics(
        actual_array,
        probability_array,
        base_array,
        persistence_array,
    )
    recent_mask = pd.DatetimeIndex(dates) >= pd.Timestamp("2018-01-01")
    result["recent2018Plus"] = _validation_metrics(
        actual_array[recent_mask],
        probability_array[recent_mask],
        base_array[recent_mask],
        persistence_array[recent_mask],
    )
    result["qualified"] = bool(
        float(result["accuracy"] or 0.0) >= 0.65
        and float(result["auc"] or 0.0) >= REGIME_AUC_GATE
        and float(result["brier"] or 1.0) < float(result["baseBrier"] or 0.0)
        and float(result["brier"] or 1.0) < float(result["persistenceBrier"] or 0.0)
        and float(result["recent2018Plus"]["accuracy"] or 0.0) >= 0.65
        and float(result["recent2018Plus"]["auc"] or 0.0) >= REGIME_AUC_GATE
        and float(result["recent2018Plus"]["brier"] or 1.0)
        < float(result["recent2018Plus"]["baseBrier"] or 0.0)
        and float(result["recent2018Plus"]["brier"] or 1.0)
        < float(result["recent2018Plus"]["persistenceBrier"] or 0.0)
    )

    current = features.dropna(subset=["state", "slope_3"]).tail(1)
    final_columns = [
        column
        for column in feature_columns
        if frame[column].notna().any() and current[column].notna().any()
    ]
    final_model = _classifier()
    final_model.fit(frame[final_columns], frame["target_risk_on"].astype(int))
    probability_risk_on = float(
        final_model.predict_proba(current[final_columns])[:, 1][0]
    )
    current_level = float(state.loc[current.index[-1]])
    risk_on_levels = frame.loc[frame["target_risk_on"] == 1, "future_state"]
    risk_off_levels = frame.loc[frame["target_risk_on"] == 0, "future_state"]

    def mixed_quantile(quantile: float) -> float:
        return float(
            probability_risk_on * risk_on_levels.quantile(quantile)
            + (1.0 - probability_risk_on) * risk_off_levels.quantile(quantile)
        )

    scenario_level = mixed_quantile(0.50)
    forecast = {
        "asOf": current.index[-1].strftime("%Y-%m"),
        "horizonMonths": horizon,
        "probabilityRiskOn": _json_value(probability_risk_on),
        "probabilityRiskOff": _json_value(1.0 - probability_risk_on),
        "direction": (
            "风险偏好状态概率占优"
            if probability_risk_on >= 0.55
            else "风险规避状态概率占优"
            if probability_risk_on <= 0.45
            else "状态概率接近均衡"
        ),
        "currentLevel": _json_value(current_level),
        "scenarioLevel": _json_value(scenario_level),
        "scenarioLow": _json_value(mixed_quantile(0.20)),
        "scenarioHigh": _json_value(mixed_quantile(0.80)),
        "qualified": result["qualified"],
    }
    return result, forecast


def _asset_validation_metrics(
    actual: np.ndarray,
    probabilities: np.ndarray,
    base_probabilities: np.ndarray,
) -> dict[str, object]:
    accuracy = float(np.mean((probabilities >= 0.5) == actual))
    brier = float(brier_score_loss(actual, probabilities))
    base_brier = float(brier_score_loss(actual, base_probabilities))
    auc = _safe_auc(actual, probabilities)
    qualified = bool(accuracy >= 0.60 and (auc or 0.0) >= 0.65 and brier < base_brier)
    return {
        "observations": int(len(actual)),
        "accuracy": _json_value(accuracy),
        "baseAccuracy": _json_value(np.mean((base_probabilities >= 0.5) == actual)),
        "brier": _json_value(brier),
        "baseBrier": _json_value(base_brier),
        "auc": _json_value(auc),
        "qualified": qualified,
    }


def _future_asset_risk(series: pd.Series, horizon: int) -> pd.Series:
    if horizon == 1:
        return series.shift(-1).abs() * math.sqrt(12.0)
    return _future_volatility(series, horizon)


def _validate_broad_asset_direction(families: pd.DataFrame) -> dict[str, object]:
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    risk_columns = returns.columns.get_level_values(0).isin(RISK_ASSET_CATEGORIES)
    broad_return = returns.loc[:, risk_columns].median(axis=1, skipna=True)
    features = _non_price_feature_frame(families)
    validations: dict[str, object] = {}
    for horizon in (1, 3, 6):
        future_return = (1.0 + broad_return).rolling(
            horizon, min_periods=horizon
        ).apply(np.prod, raw=True).shift(-horizon) - 1.0
        target = (future_return > 0).astype(float).where(future_return.notna())
        frame = features.join(target.rename("target_up")).dropna(
            subset=["交易活跃", "融资拥挤", "外部避险", "target_up"]
        )
        probabilities: list[float] = []
        actual: list[int] = []
        base_probabilities: list[float] = []
        feature_columns = list(features.columns)
        for current_date in frame.index:
            train = frame.loc[
                frame.index <= current_date - pd.DateOffset(months=horizon)
            ]
            test = frame.loc[[current_date]]
            if len(train) < 60 or train["target_up"].nunique() < 2:
                continue
            eligible_columns = [
                column
                for column in feature_columns
                if train[column].notna().any() and test[column].notna().any()
            ]
            model = _classifier()
            model.fit(train[eligible_columns], train["target_up"].astype(int))
            probabilities.append(
                float(model.predict_proba(test[eligible_columns])[:, 1][0])
            )
            actual.append(int(test["target_up"].iloc[0]))
            base_probabilities.append(float(train["target_up"].mean()))
        validations[f"{horizon}m"] = _asset_validation_metrics(
            np.asarray(actual),
            np.asarray(probabilities),
            np.asarray(base_probabilities),
        )
    passed_horizons = [
        horizon for horizon, result in validations.items() if result["qualified"]
    ]
    return {
        "target": "非价格信号预测广义风险资产未来1、3、6个月累计收益方向",
        "features": ["成交活跃度", "融资余额加速度", "美元避险压力"],
        "validation": validations,
        "passedHorizons": passed_horizons,
    }


def validate_asset_direction(families: pd.DataFrame) -> dict[str, object]:
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    broad_validation = _validate_broad_asset_direction(families)

    signal_families = families[["交易活跃", "融资拥挤", "外部避险"]]
    signal_state = signal_families.mean(axis=1, skipna=True).where(
        signal_families.notna().sum(axis=1) >= 2
    )
    signal_features = _non_price_feature_frame(families)
    signal_features["state"] = signal_state.shift(1)
    signal_features["slope_3"] = (signal_state.diff(3) / 3.0).shift(1)

    cells: list[dict[str, object]] = []
    for asset_group, categories in C7_ASSET_GROUPS.items():
        columns = returns.columns.get_level_values(0).isin(categories)
        group_return = returns.loc[:, columns].median(axis=1, skipna=True)
        baseline = _asset_baseline_features(group_return, signal_features.index)
        augmented = baseline.join(signal_features, how="left")
        for horizon in HEADLINE_HORIZONS:
            return_validation = _asset_direction_robust_validation(
                baseline,
                augmented,
                _future_return(group_return, horizon),
                horizon,
            )
            risk_validation = _asset_risk_validation(
                baseline,
                augmented,
                _future_asset_risk(group_return, horizon),
                horizon,
            )
            cells.append(
                {
                    "assetGroup": asset_group,
                    "horizonMonths": horizon,
                    "assetCount": int(columns.sum()),
                    "riskTarget": (
                        "未来1个月年化绝对波动代理"
                        if horizon == 1
                        else f"未来{horizon}个月实现波动"
                    ),
                    "returnDirection": return_validation,
                    "volatility": risk_validation,
                }
            )

    return_passed = sum(bool(cell["returnDirection"]["passed"]) for cell in cells)
    risk_passed = sum(bool(cell["volatility"]["passed"]) for cell in cells)
    passed_groups = {
        str(cell["assetGroup"])
        for cell in cells
        if cell["returnDirection"]["passed"] or cell["volatility"]["passed"]
    }
    required_groups = {"中国股票", "海外股票", "债券", "商品"}
    unlock = return_passed + risk_passed >= 6 and required_groups.issubset(
        passed_groups
    )
    return {
        "status": "research_only" if unlock else "blocked",
        **broad_validation,
        "method": (
            "按中国股票、海外股票、债券、商品和外汇分别检验1/3/6个月收益方向与未来波动；"
            "1个月风险使用下一月绝对收益年化代理，3/6个月使用未来实现波动；"
            "资产方向使用固定多正则强度概率集成，并要求三个参数带同时通过；"
            "资产自身动量和波动为基线，仅成交活跃、融资拥挤和美元避险三组滞后信号作为C7增量。"
        ),
        "summary": {
            "assetGroups": len(C7_ASSET_GROUPS),
            "horizons": list(HEADLINE_HORIZONS),
            "returnChannelsPassed": int(return_passed),
            "riskChannelsPassed": int(risk_passed),
            "passedChannels": int(return_passed + risk_passed),
            "totalChannels": int(len(cells) * 2),
        },
        "cells": cells,
        "caveat": (
            "市场收益、风格收益和完整C7状态不进入增量特征，避免价格循环验证；"
            "30个通道未形成跨资产组稳定通过前，不输出资产绝对收益、风险预测或配置权重。"
        ),
    }


def _regime(level: float, slope: float) -> str:
    if level > 0.35:
        return "风险偏好高位降温" if slope < -0.03 else "风险偏好扩张"
    if level < -0.35:
        return "风险规避修复" if slope > 0.03 else "风险规避加深"
    if slope > 0.05:
        return "中性转强"
    if slope < -0.05:
        return "中性转弱"
    return "中性震荡"


def build_payload() -> dict[str, object]:
    panel = _monthly_panel()
    families, state = build_risk_appetite_state(panel)
    path_validations: dict[int, dict[str, object]] = {}
    path_forecasts: dict[int, dict[str, object]] = {}
    for horizon in FORECAST_PATH_HORIZONS:
        validation, forecast = validate_regime_probability(families, state, horizon)
        path_validations[horizon] = validation
        path_forecasts[horizon] = forecast
    validations = {
        f"{horizon}m": path_validations[horizon]
        for horizon in HEADLINE_HORIZONS
    }
    forecasts = [path_forecasts[horizon] for horizon in HEADLINE_HORIZONS]
    forecast_path = [path_forecasts[horizon] for horizon in FORECAST_PATH_HORIZONS]
    slope_1 = state.diff()
    slope_3 = state.diff(3) / 3.0
    family_disagreement = families.std(axis=1, ddof=0)
    timeline = pd.DataFrame(
        {
            "date": state.index.strftime("%Y-%m"),
            "state": state.to_numpy(),
            "slope1": slope_1.to_numpy(),
            "slope3": slope_3.to_numpy(),
            "familyDisagreement": family_disagreement.reindex(state.index).to_numpy(),
        }
    ).dropna(subset=["state"])
    timeline["regime"] = [
        _regime(float(level), float(slope) if np.isfinite(slope) else 0.0)
        for level, slope in zip(timeline["state"], timeline["slope3"], strict=True)
    ]
    latest = timeline.iloc[-1]
    qualified_horizons = [
        forecast["horizonMonths"]
        for forecast in forecast_path
        if forecast["qualified"]
    ]
    asset_validation = validate_asset_direction(families)
    return {
        "meta": {
            "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
            "asOf": latest["date"],
            "definition": "C7=收益、风格、成交、融资拥挤、美元避险、波动与信用压力共同形成的快速风险偏好状态；不假设固定6个月周期。",
            "publicSignals": ["FRED:VIXCLS", "FRED:NFCI", "FRED:BAA-AAA"],
            "regimeAucGate": REGIME_AUC_GATE,
            "featureTiming": "状态与市场信号使用当月月末可观测值，不再整体额外滞后一个月；五类资产收益风险验证仅使用滞后一月的成交、融资与美元避险信号。",
        },
        "status": (
            "short_horizon_regime_predictable"
            if {1, 2, 3, 4, 5}.issubset(qualified_horizons)
            else "research_only"
        ),
        "publicationStatus": "limited",
        "current": {
            "date": latest["date"],
            "level": _json_value(latest["state"]),
            "slope1": _json_value(latest["slope1"]),
            "slope3": _json_value(latest["slope3"]),
            "regime": latest["regime"],
            "familyDisagreement": _json_value(latest["familyDisagreement"]),
            "familyValues": {
                column: _json_value(families[column].reindex(state.index).iloc[-1])
                for column in families
            },
        },
        "timeline": _records(timeline),
        "familyCoverage": [
            {
                "family": column,
                "start": _json_value(families[column].first_valid_index()),
                "end": _json_value(families[column].last_valid_index()),
                "observations": int(families[column].notna().sum()),
            }
            for column in families
        ],
        "validation": validations,
        "pathValidation": {
            f"{horizon}m": {
                "accuracy": path_validations[horizon]["accuracy"],
                "auc": path_validations[horizon]["auc"],
                "brier": path_validations[horizon]["brier"],
                "qualified": path_validations[horizon]["qualified"],
            }
            for horizon in FORECAST_PATH_HORIZONS
        },
        "currentForecasts": forecasts,
        "forecastPath": forecast_path,
        "assetValidation": asset_validation,
        "governance": {
            "formalCycleStatus": "blocked",
            "stateStatus": "limited" if qualified_horizons else "blocked",
            "assetForecastStatus": (
                "blocked"
                if asset_validation["status"] == "blocked"
                else "research_only"
            ),
            "notAllowed": [
                "固定6个月相位角",
                "把风险偏好状态当作独立资产因果因子",
                "把未来仍处风险偏好区间的概率解释为状态继续上行",
                "发布未通过门槛的6个月路径",
                "用市场收益或风格收益循环验证资产通道",
            ],
        },
        "caveat": "1至5个月未来状态处于风险偏好区间的概率通过准确率、AUC、Brier与近年留出门槛；该概率不是状态继续上行概率。6个月状态以及五类资产1/3/6个月收益风险增量必须单独通过，未通过前不能扩展为资产预测。",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-public", action="store_true")
    args = parser.parse_args()
    if args.refresh_public:
        _refresh_public_signals()
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote: {OUTPUT_PATH}")
    print("status=", payload["status"], "current=", payload["current"])
    for horizon, validation in payload["validation"].items():
        print(
            horizon,
            "accuracy=",
            validation["accuracy"],
            "auc=",
            validation["auc"],
            "qualified=",
            validation["qualified"],
        )
    print("asset=", payload["assetValidation"]["status"])


if __name__ == "__main__":
    main()
