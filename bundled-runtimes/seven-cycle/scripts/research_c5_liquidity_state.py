"""Build the governed C5 liquidity-state research model.

C5 is a three-layer liquidity state rather than a fixed 20-month sine wave.
Domestic policy liquidity, credit transmission and global dollar liquidity
form the core state. NFCI is kept outside the core as an independent check.
"""

from __future__ import annotations

from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PANEL_PATH = PROJECT_ROOT / "data" / "indicator_panel_monthly.parquet"
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c5_liquidity_state_research.json"

CORE_FAMILIES = ("国内政策流动性", "信用传导", "全球美元流动性")
STATE_VALIDATION_HORIZONS = (3, 6, 12)
FORECAST_PATH_HORIZONS = tuple(range(1, 13))
MIN_STATE_TRAIN = 72
MIN_ASSET_TRAIN = 72
ASSET_CLASSIFIER_REGULARIZATION_BANDS = {
    "strong": (0.005, 0.01, 0.02),
    "central": (0.01, 0.02, 0.05),
    "light": (0.02, 0.05, 0.10),
}
ASSET_CLASSIFIER_PRIMARY_BAND = "central"

ASSET_GROUPS = {
    "中国股票": {"A股宽基指数", "申万一级行业", "风格/规模指数"},
    "海外股票": {"海外指数/ETF", "美股行业ETF", "FF 17行业组合(US)"},
    "债券": {"各类债券指数"},
    "商品": {"商品"},
    "外汇": {"外汇"},
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


def _family_factor(signals: pd.DataFrame, *, minimum_signals: int = 2) -> pd.Series:
    return signals.mean(axis=1, skipna=True).where(
        signals.notna().sum(axis=1) >= minimum_signals
    )


def _segmented_ewm(
    series: pd.Series,
    *,
    span: int,
    min_periods: int,
) -> pd.Series:
    valid = series.notna()
    groups = valid.ne(valid.shift(fill_value=False)).cumsum()
    smoothed = series.groupby(groups).transform(
        lambda values: values.ewm(
            span=span,
            adjust=False,
            min_periods=min_periods,
        ).mean()
    )
    return smoothed.where(valid)


def build_liquidity_state(
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, dict[str, pd.DataFrame], pd.Series]:
    m1 = pd.to_numeric(panel["CN_M_M1_YOY"], errors="coerce")
    m2 = pd.to_numeric(panel["CN_M_M2_YOY"], errors="coerce")
    domestic_signals = pd.concat(
        {
            "M2增速": _causal_robust_z(m2),
            "M2三月脉冲": _causal_robust_z(m2.diff(3) / 3.0),
            "LPR宽松脉冲": _causal_robust_z(
                -pd.to_numeric(panel["CN_LPR_1Y_AK_LEVEL"], errors="coerce").diff(3)
                / 3.0
            ),
            "SHIBOR宽松脉冲": _causal_robust_z(
                -pd.to_numeric(panel["CN_SHIBOR_ON_AK_LEVEL"], errors="coerce").diff(3)
                / 3.0
            ),
            "R007宽松脉冲": _causal_robust_z(
                -pd.to_numeric(panel["CN_REPO_R007_LEVEL"], errors="coerce").diff(3)
                / 3.0
            ),
        },
        axis=1,
    )
    credit_signals = pd.concat(
        {
            "M1增速": _causal_robust_z(m1),
            "M1-M2剪刀差": _causal_robust_z(m1 - m2),
            "社融存量增速": _causal_robust_z(panel["CN_SF_STOCK_YOY"]),
            "十二月社融流量增速": _causal_robust_z(panel["CN_SF_FLOW12_YOY"]),
        },
        axis=1,
    )
    broad_dollar = pd.to_numeric(panel["US_BROAD_DOLLAR_LEVEL"], errors="coerce")
    global_signals = pd.concat(
        {
            "联邦基金宽松脉冲": _causal_robust_z(
                -pd.to_numeric(panel["US_FEDFUNDS_LEVEL"], errors="coerce").diff(3)
                / 3.0
            ),
            "美元宽松脉冲": _causal_robust_z(
                -broad_dollar.pct_change(3, fill_method=None) / 3.0
            ),
            "美联储资产负债表增速": _causal_robust_z(panel["US_FED_BALANCE_SHEET_YOY"]),
        },
        axis=1,
    )
    signals = {
        "国内政策流动性": domestic_signals,
        "信用传导": credit_signals,
        "全球美元流动性": global_signals,
    }
    families = pd.concat(
        {
            family: _family_factor(family_signals)
            for family, family_signals in signals.items()
        },
        axis=1,
    )
    composite = families.mean(axis=1).where(families.notna().all(axis=1))
    state = _segmented_ewm(composite, span=4, min_periods=3)
    confirmation = _causal_robust_z(-panel["US_NFCI_LEVEL"])
    return families, state, signals, confirmation


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


def _classifier() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        LogisticRegression(
            C=0.05,
            max_iter=2_000,
            class_weight="balanced",
        ),
    )


class _RegularizationEnsembleClassifier:
    def __init__(self, regularization_values: tuple[float, ...]) -> None:
        self.regularization_values = regularization_values
        self.models: list[object] = []

    def fit(self, features: pd.DataFrame, target: pd.Series) -> object:
        self.models = [
            make_pipeline(
                SimpleImputer(strategy="median", add_indicator=True),
                StandardScaler(),
                LogisticRegression(
                    C=regularization_value,
                    max_iter=2_000,
                ),
            )
            for regularization_value in self.regularization_values
        ]
        for model in self.models:
            model.fit(features, target)
        return self

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        return np.mean(
            [model.predict_proba(features) for model in self.models],
            axis=0,
        )


def _asset_classifier(
    regularization_values: tuple[float, ...],
) -> _RegularizationEnsembleClassifier:
    return _RegularizationEnsembleClassifier(regularization_values)


def _regressor() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        Ridge(alpha=20.0),
    )


def _safe_auc(actual: np.ndarray, probabilities: np.ndarray) -> float | None:
    if len(np.unique(actual)) < 2:
        return None
    return float(roc_auc_score(actual, probabilities))


def _direction_metrics(
    actual: np.ndarray,
    probabilities: np.ndarray,
    base_probabilities: np.ndarray,
    momentum: np.ndarray,
) -> dict[str, object]:
    if len(actual) == 0:
        return {
            "observations": 0,
            "accuracy": None,
            "momentumAccuracy": None,
            "baseAccuracy": None,
            "brier": None,
            "baseBrier": None,
            "momentumBrier": None,
            "auc": None,
        }
    return {
        "observations": int(len(actual)),
        "accuracy": _json_value(np.mean((probabilities >= 0.5) == actual)),
        "momentumAccuracy": _json_value(np.mean(momentum == actual)),
        "baseAccuracy": _json_value(np.mean((base_probabilities >= 0.5) == actual)),
        "brier": _json_value(brier_score_loss(actual, probabilities)),
        "baseBrier": _json_value(brier_score_loss(actual, base_probabilities)),
        "momentumBrier": _json_value(brier_score_loss(actual, momentum.astype(float))),
        "auc": _json_value(_safe_auc(actual, probabilities)),
    }


def _walk_forward_state_direction(
    features: pd.DataFrame,
    state: pd.Series,
    horizon: int,
) -> dict[str, object]:
    target = (
        (state.shift(-horizon) > state)
        .astype(float)
        .where(state.shift(-horizon).notna() & state.notna())
    )
    frame = features.join(target.rename("target_up")).dropna(
        subset=["state", "slope_3", "target_up"]
    )
    feature_columns = list(features.columns)
    probabilities: list[float] = []
    base_probabilities: list[float] = []
    actual: list[int] = []
    momentum: list[int] = []
    dates: list[pd.Timestamp] = []
    for current_date in frame.index:
        train = frame.loc[frame.index <= current_date - pd.DateOffset(months=horizon)]
        test = frame.loc[[current_date]]
        if len(train) < MIN_STATE_TRAIN or train["target_up"].nunique() < 2:
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
        base_probabilities.append(float(train["target_up"].mean()))
        actual.append(int(test["target_up"].iloc[0]))
        momentum.append(int(test["slope_3"].iloc[0] > 0))
        dates.append(pd.Timestamp(current_date))

    probability_array = np.asarray(probabilities)
    base_array = np.asarray(base_probabilities)
    actual_array = np.asarray(actual)
    momentum_array = np.asarray(momentum)
    date_index = pd.DatetimeIndex(dates)
    result = _direction_metrics(
        actual_array,
        probability_array,
        base_array,
        momentum_array,
    )
    recent_mask = date_index >= pd.Timestamp("2018-01-01")
    recent = _direction_metrics(
        actual_array[recent_mask],
        probability_array[recent_mask],
        base_array[recent_mask],
        momentum_array[recent_mask],
    )
    result["recent2018Plus"] = recent
    gates = {
        "observations_at_least_96": int(result["observations"]) >= 96,
        "accuracy_at_least_60": float(result["accuracy"] or 0.0) >= 0.60,
        "auc_at_least_68": float(result["auc"] or 0.0) >= 0.68,
        "brier_beats_base": float(result["brier"] or 1.0)
        < float(result["baseBrier"] or 0.0),
        "brier_beats_momentum": float(result["brier"] or 1.0)
        < float(result["momentumBrier"] or 0.0),
        "recent_accuracy_at_least_60": float(recent["accuracy"] or 0.0) >= 0.60,
        "recent_auc_at_least_68": float(recent["auc"] or 0.0) >= 0.68,
        "recent_brier_beats_base": float(recent["brier"] or 1.0)
        < float(recent["baseBrier"] or 0.0),
        "recent_brier_beats_momentum": float(recent["brier"] or 1.0)
        < float(recent["momentumBrier"] or 0.0),
    }
    result["gates"] = gates
    result["qualified"] = all(gates.values())
    return result


def _current_state_forecast(
    features: pd.DataFrame,
    state: pd.Series,
    horizon: int,
    *,
    qualified: bool,
) -> dict[str, object]:
    target = (
        (state.shift(-horizon) > state)
        .astype(float)
        .where(state.shift(-horizon).notna() & state.notna())
    )
    frame = features.join(target.rename("target_up")).dropna(
        subset=["state", "slope_3", "target_up"]
    )
    current_date = state.last_valid_index()
    if current_date is None:
        raise RuntimeError("C5 current state unavailable")
    current = features.loc[[current_date]]
    eligible_columns = [
        column
        for column in features.columns
        if frame[column].notna().any() and current[column].notna().any()
    ]
    model = _classifier()
    model.fit(frame[eligible_columns], frame["target_up"].astype(int))
    probability_up = float(model.predict_proba(current[eligible_columns])[:, 1][0])
    changes = (state.shift(-horizon) - state).dropna()
    positive_changes = changes.loc[changes > 0]
    negative_changes = changes.loc[changes <= 0]
    positive_median = float(
        positive_changes.median()
        if not positive_changes.empty
        else changes.quantile(0.75)
    )
    negative_median = float(
        negative_changes.median()
        if not negative_changes.empty
        else changes.quantile(0.25)
    )
    current_level = float(state.loc[current_date])
    expected_change = (
        probability_up * positive_median + (1.0 - probability_up) * negative_median
    )
    return {
        "asOf": current_date.strftime("%Y-%m"),
        "horizonMonths": horizon,
        "probabilityUp": _json_value(probability_up),
        "probabilityDown": _json_value(1.0 - probability_up),
        "direction": (
            "状态上行概率占优"
            if probability_up >= 0.55
            else "状态下行概率占优"
            if probability_up <= 0.45
            else "方向接近均衡"
        ),
        "currentLevel": _json_value(current_level),
        "scenarioLevel": _json_value(current_level + expected_change),
        "scenarioLow": _json_value(current_level + changes.quantile(0.20)),
        "scenarioHigh": _json_value(current_level + changes.quantile(0.80)),
        "qualified": qualified,
    }


def _ablation_validation(
    families: pd.DataFrame,
    state: pd.Series,
    full_validation: dict[str, dict[str, object]],
) -> dict[str, object]:
    horizons: dict[str, list[dict[str, object]]] = {}
    removal_improvements: list[float] = []
    for horizon in (6, 12):
        rows: list[dict[str, object]] = []
        full_auc = float(full_validation[f"{horizon}m"]["auc"] or 0.0)
        full_brier = float(full_validation[f"{horizon}m"]["brier"] or 1.0)
        for family in CORE_FAMILIES:
            reduced_features = _feature_frame(
                families.drop(columns=[family]),
                state,
            )
            metrics = _walk_forward_state_direction(
                reduced_features,
                state,
                horizon,
            )
            auc = float(metrics["auc"] or 0.0)
            brier = float(metrics["brier"] or 1.0)
            removal_improvements.append(auc - full_auc)
            rows.append(
                {
                    "removedFamily": family,
                    "accuracy": metrics["accuracy"],
                    "auc": metrics["auc"],
                    "brier": metrics["brier"],
                    "aucChangeVsFull": _json_value(auc - full_auc),
                    "brierChangeVsFull": _json_value(brier - full_brier),
                }
            )
        horizons[f"{horizon}m"] = rows
    sensitive = max(removal_improvements, default=0.0) > 0.01
    return {
        "status": "mixed_redundancy" if sensitive else "stable_three_layer",
        "horizons": horizons,
        "caveat": (
            "删去任一层后仍保留状态自身滞后项；该检验识别新增信息，不把单层相关性解释为因果贡献。"
        ),
    }


def _binary_metrics(
    actual: np.ndarray,
    probabilities: np.ndarray,
) -> dict[str, object]:
    if len(actual) == 0:
        return {
            "observations": 0,
            "accuracy": None,
            "auc": None,
            "brier": None,
        }
    return {
        "observations": int(len(actual)),
        "accuracy": _json_value(np.mean((probabilities >= 0.5) == actual)),
        "auc": _json_value(_safe_auc(actual, probabilities)),
        "brier": _json_value(brier_score_loss(actual, probabilities)),
    }


def _asset_baseline_features(
    returns: pd.Series,
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    asset = pd.to_numeric(returns, errors="coerce").reindex(index)
    features = pd.DataFrame(index=index)
    features["asset_return_1m"] = asset
    features["asset_momentum_3m"] = (1.0 + asset).rolling(3, min_periods=3).apply(
        np.prod, raw=True
    ) - 1.0
    features["asset_momentum_6m"] = (1.0 + asset).rolling(6, min_periods=6).apply(
        np.prod, raw=True
    ) - 1.0
    features["asset_volatility_6m"] = asset.rolling(6, min_periods=4).std(ddof=1)
    features["asset_volatility_12m"] = asset.rolling(12, min_periods=8).std(ddof=1)
    features["month_sin"] = np.sin(2.0 * np.pi * features.index.month / 12.0)
    features["month_cos"] = np.cos(2.0 * np.pi * features.index.month / 12.0)
    return features.shift(1)


def _future_return(series: pd.Series, horizon: int) -> pd.Series:
    return (1.0 + series).rolling(horizon, min_periods=horizon).apply(
        np.prod, raw=True
    ).shift(-horizon) - 1.0


def _future_volatility(series: pd.Series, horizon: int) -> pd.Series:
    future = pd.concat(
        [series.shift(-month) for month in range(1, horizon + 1)],
        axis=1,
    )
    return future.std(axis=1, ddof=1).where(
        future.notna().sum(axis=1) == horizon
    ) * math.sqrt(12.0)


def _asset_direction_validation(
    baseline: pd.DataFrame,
    augmented: pd.DataFrame,
    target: pd.Series,
    horizon: int,
    *,
    regularization_values: tuple[float, ...],
) -> dict[str, object]:
    frame = augmented.join(target.rename("target_return")).dropna(
        subset=["asset_return_1m", "state", "slope_3", "target_return"]
    )
    baseline_columns = list(baseline.columns)
    augmented_columns = list(augmented.columns)
    probabilities = {"baseline": [], "augmented": []}
    actual: list[int] = []
    dates: list[pd.Timestamp] = []
    for current_date in frame.index:
        train = frame.loc[frame.index <= current_date - pd.DateOffset(months=horizon)]
        test = frame.loc[[current_date]]
        target_up = train["target_return"] > 0
        if len(train) < MIN_ASSET_TRAIN or target_up.nunique() < 2:
            continue
        actual.append(int(test["target_return"].iloc[0] > 0))
        dates.append(pd.Timestamp(current_date))
        for model_name, columns in (
            ("baseline", baseline_columns),
            ("augmented", augmented_columns),
        ):
            eligible_columns = [
                column
                for column in columns
                if train[column].notna().any() and test[column].notna().any()
            ]
            model = _asset_classifier(regularization_values)
            model.fit(train[eligible_columns], target_up.astype(int))
            probabilities[model_name].append(
                float(model.predict_proba(test[eligible_columns])[:, 1][0])
            )

    actual_array = np.asarray(actual)
    date_index = pd.DatetimeIndex(dates)
    baseline_array = np.asarray(probabilities["baseline"])
    augmented_array = np.asarray(probabilities["augmented"])

    def comparison(mask: np.ndarray) -> dict[str, object]:
        base = _binary_metrics(actual_array[mask], baseline_array[mask])
        model = _binary_metrics(actual_array[mask], augmented_array[mask])
        auc_improvement = (
            float(model["auc"]) - float(base["auc"])
            if model["auc"] is not None and base["auc"] is not None
            else None
        )
        brier_improvement = (
            float(base["brier"]) - float(model["brier"])
            if model["brier"] is not None and base["brier"] is not None
            else None
        )
        return {
            "baseline": base,
            "augmented": model,
            "aucImprovement": _json_value(auc_improvement),
            "brierImprovement": _json_value(brier_improvement),
        }

    overall = comparison(np.ones(len(actual_array), dtype=bool))
    recent = comparison(date_index >= pd.Timestamp("2018-01-01"))
    gates = {
        "observations_at_least_72": int(overall["augmented"]["observations"]) >= 72,
        "accuracy_at_least_55": float(overall["augmented"]["accuracy"] or 0.0) >= 0.55,
        "auc_at_least_58": float(overall["augmented"]["auc"] or 0.0) >= 0.58,
        "auc_improvement_at_least_02": float(overall["aucImprovement"] or 0.0) >= 0.02,
        "brier_improvement_at_least_002": float(overall["brierImprovement"] or 0.0)
        >= 0.002,
        "recent_auc_not_worse": recent["aucImprovement"] is not None
        and float(recent["aucImprovement"]) >= 0.0,
        "recent_brier_better": float(recent["brierImprovement"] or 0.0) > 0.0,
    }
    return {
        **overall,
        "recent2018Plus": recent,
        "gates": gates,
        "passed": all(gates.values()),
    }


def _asset_direction_robust_validation(
    baseline: pd.DataFrame,
    augmented: pd.DataFrame,
    target: pd.Series,
    horizon: int,
) -> dict[str, object]:
    validations = {
        band: _asset_direction_validation(
            baseline,
            augmented,
            target,
            horizon,
            regularization_values=regularization_values,
        )
        for band, regularization_values in ASSET_CLASSIFIER_REGULARIZATION_BANDS.items()
    }
    primary = validations[ASSET_CLASSIFIER_PRIMARY_BAND]
    stable = all(validation["passed"] for validation in validations.values())
    primary["gates"]["regularization_bands_stable"] = stable
    primary["passed"] = all(primary["gates"].values())
    primary["regularizationRobustness"] = {
        "primaryBand": ASSET_CLASSIFIER_PRIMARY_BAND,
        "stable": stable,
        "bands": {
            band: {
                "regularizationValues": list(
                    ASSET_CLASSIFIER_REGULARIZATION_BANDS[band]
                ),
                "passed": validation["passed"],
                "accuracy": validation["augmented"]["accuracy"],
                "auc": validation["augmented"]["auc"],
                "brierImprovement": validation["brierImprovement"],
                "recentAucImprovement": validation["recent2018Plus"][
                    "aucImprovement"
                ],
                "recentBrierImprovement": validation["recent2018Plus"][
                    "brierImprovement"
                ],
            }
            for band, validation in validations.items()
        },
    }
    return primary


def _risk_metrics(
    actual: np.ndarray,
    baseline: np.ndarray,
    augmented: np.ndarray,
) -> dict[str, object]:
    if len(actual) == 0:
        return {
            "observations": 0,
            "baselineMae": None,
            "augmentedMae": None,
            "maeImprovement": None,
            "incrementalOosR2": None,
        }
    baseline_mae = float(np.mean(np.abs(actual - baseline)))
    augmented_mae = float(np.mean(np.abs(actual - augmented)))
    baseline_error = float(np.sum((actual - baseline) ** 2))
    augmented_error = float(np.sum((actual - augmented) ** 2))
    return {
        "observations": int(len(actual)),
        "baselineMae": _json_value(baseline_mae),
        "augmentedMae": _json_value(augmented_mae),
        "maeImprovement": _json_value(
            (baseline_mae - augmented_mae) / baseline_mae if baseline_mae > 0 else None
        ),
        "incrementalOosR2": _json_value(
            1.0 - augmented_error / baseline_error if baseline_error > 0 else None
        ),
    }


def _asset_risk_validation(
    baseline: pd.DataFrame,
    augmented: pd.DataFrame,
    target: pd.Series,
    horizon: int,
) -> dict[str, object]:
    frame = augmented.join(target.rename("target_risk")).dropna(
        subset=["asset_return_1m", "state", "slope_3", "target_risk"]
    )
    baseline_columns = list(baseline.columns)
    augmented_columns = list(augmented.columns)
    predictions = {"baseline": [], "augmented": []}
    actual: list[float] = []
    dates: list[pd.Timestamp] = []
    for current_date in frame.index:
        train = frame.loc[frame.index <= current_date - pd.DateOffset(months=horizon)]
        test = frame.loc[[current_date]]
        if len(train) < MIN_ASSET_TRAIN:
            continue
        actual.append(float(test["target_risk"].iloc[0]))
        dates.append(pd.Timestamp(current_date))
        for model_name, columns in (
            ("baseline", baseline_columns),
            ("augmented", augmented_columns),
        ):
            eligible_columns = [
                column
                for column in columns
                if train[column].notna().any() and test[column].notna().any()
            ]
            model = _regressor()
            model.fit(
                train[eligible_columns],
                np.log(train["target_risk"].clip(lower=1e-5)),
            )
            predictions[model_name].append(
                float(np.exp(model.predict(test[eligible_columns])[0]))
            )

    actual_array = np.asarray(actual)
    baseline_array = np.asarray(predictions["baseline"])
    augmented_array = np.asarray(predictions["augmented"])
    date_index = pd.DatetimeIndex(dates)
    overall = _risk_metrics(actual_array, baseline_array, augmented_array)
    recent_mask = date_index >= pd.Timestamp("2018-01-01")
    recent = _risk_metrics(
        actual_array[recent_mask],
        baseline_array[recent_mask],
        augmented_array[recent_mask],
    )
    gates = {
        "observations_at_least_72": int(overall["observations"]) >= 72,
        "incremental_oos_r2_above_01": float(overall["incrementalOosR2"] or 0.0) > 0.01,
        "mae_improvement_above_half_percent": float(overall["maeImprovement"] or 0.0)
        > 0.005,
        "recent_incremental_oos_r2_positive": float(recent["incrementalOosR2"] or 0.0)
        > 0.0,
        "recent_mae_improvement_positive": float(recent["maeImprovement"] or 0.0) > 0.0,
    }
    return {
        **overall,
        "recent2018Plus": recent,
        "gates": gates,
        "passed": all(gates.values()),
    }


def validate_asset_direction(
    families: pd.DataFrame,
    state: pd.Series,
) -> dict[str, object]:
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    state_features = _feature_frame(families, state).shift(1)
    cells: list[dict[str, object]] = []
    for asset_group, categories in ASSET_GROUPS.items():
        columns = returns.columns.get_level_values(0).isin(categories)
        group_return = returns.loc[:, columns].median(axis=1, skipna=True)
        baseline = _asset_baseline_features(group_return, state_features.index)
        augmented = baseline.join(state_features, how="left")
        for horizon in STATE_VALIDATION_HORIZONS:
            return_validation = _asset_direction_robust_validation(
                baseline,
                augmented,
                _future_return(group_return, horizon),
                horizon,
            )
            risk_validation = _asset_risk_validation(
                baseline,
                augmented,
                _future_volatility(group_return, horizon),
                horizon,
            )
            cells.append(
                {
                    "assetGroup": asset_group,
                    "horizonMonths": horizon,
                    "assetCount": int(columns.sum()),
                    "returnDirection": return_validation,
                    "volatility": risk_validation,
                }
            )

    return_passed = sum(bool(cell["returnDirection"]["passed"]) for cell in cells)
    risk_passed = sum(bool(cell["volatility"]["passed"]) for cell in cells)
    passed_groups = {
        cell["assetGroup"]
        for cell in cells
        if cell["returnDirection"]["passed"] or cell["volatility"]["passed"]
    }
    required_groups = {"中国股票", "海外股票", "债券", "商品"}
    unlock = return_passed + risk_passed >= 6 and required_groups.issubset(
        passed_groups
    )
    return {
        "status": "research_only" if unlock else "blocked",
        "method": (
            "按中国股票、海外股票、债券、商品和外汇分别检验3/6/12个月收益方向与未来波动；"
            "资产方向使用固定多正则强度概率集成，并要求三个参数带同时通过；"
            "资产自身动量和波动为基线，只有C5带来稳定样本外增量才算通过。"
        ),
        "summary": {
            "assetGroups": len(ASSET_GROUPS),
            "horizons": list(STATE_VALIDATION_HORIZONS),
            "returnChannelsPassed": int(return_passed),
            "riskChannelsPassed": int(risk_passed),
            "passedChannels": int(return_passed + risk_passed),
            "totalChannels": int(len(cells) * 2),
        },
        "cells": cells,
        "caveat": (
            "大类资产增量门槛未同时通过时，C5不得转换为资产绝对收益、风险预测或配置权重。"
        ),
    }


def _regime(level: float, slope: float) -> str:
    if level > 0.20:
        return "宽松充裕" if slope >= 0 else "宽松回落"
    if level < -0.20:
        return "紧张修复" if slope >= 0 else "紧张加剧"
    return "中性改善" if slope > 0.03 else "中性收紧" if slope < -0.03 else "中性稳定"


def _confirmation_payload(
    state: pd.Series,
    confirmation: pd.Series,
) -> dict[str, object]:
    aligned = pd.concat(
        [state.rename("state"), confirmation.rename("confirmation")],
        axis=1,
    ).dropna()
    current = aligned.iloc[-1]
    same_direction = bool(np.sign(current["state"]) == np.sign(current["confirmation"]))
    return {
        "indicator": "美国NFCI反向标准化",
        "role": "独立确认，不进入C5核心",
        "observations": int(len(aligned)),
        "correlation": _json_value(aligned.corr().iloc[0, 1]),
        "signAgreement": _json_value(
            (np.sign(aligned["state"]) == np.sign(aligned["confirmation"])).mean()
        ),
        "current": {
            "date": aligned.index[-1].strftime("%Y-%m"),
            "value": _json_value(current["confirmation"]),
            "status": "同向确认" if same_direction else "方向分歧",
        },
    }


def build_payload() -> dict[str, object]:
    panel = _monthly_panel()
    families, state, signals, confirmation = build_liquidity_state(panel)
    features = _feature_frame(families, state)
    path_validations: dict[int, dict[str, object]] = {}
    path_forecasts: dict[int, dict[str, object]] = {}
    for horizon in FORECAST_PATH_HORIZONS:
        validation = _walk_forward_state_direction(features, state, horizon)
        path_validations[horizon] = validation
        path_forecasts[horizon] = _current_state_forecast(
            features,
            state,
            horizon,
            qualified=bool(validation["qualified"]),
        )
    validations = {
        f"{horizon}m": path_validations[horizon]
        for horizon in STATE_VALIDATION_HORIZONS
    }
    forecasts = [path_forecasts[horizon] for horizon in STATE_VALIDATION_HORIZONS]
    forecast_path = [path_forecasts[horizon] for horizon in FORECAST_PATH_HORIZONS]

    slope_3 = state.diff(3) / 3.0
    family_disagreement = families.std(axis=1, ddof=0)
    family_counts = {
        family: family_signals.notna().sum(axis=1)
        for family, family_signals in signals.items()
    }
    timeline = pd.DataFrame(
        {
            "date": state.index.strftime("%Y-%m"),
            "state": state.to_numpy(),
            "slope3": slope_3.to_numpy(),
            "familyDisagreement": family_disagreement.reindex(state.index).to_numpy(),
            "domesticPolicy": families["国内政策流动性"].to_numpy(),
            "creditTransmission": families["信用传导"].to_numpy(),
            "globalDollar": families["全球美元流动性"].to_numpy(),
            "nfciConfirmation": confirmation.reindex(state.index).to_numpy(),
        }
    ).dropna(subset=["state"])
    timeline["regime"] = [
        _regime(float(level), float(slope) if np.isfinite(slope) else 0.0)
        for level, slope in zip(timeline["state"], timeline["slope3"], strict=True)
    ]
    latest = timeline.iloc[-1]
    latest_date = pd.Period(latest["date"], freq="M").to_timestamp("M")
    asset_validation = validate_asset_direction(families, state)
    core_qualified = all(
        validations[f"{horizon}m"]["qualified"] for horizon in STATE_VALIDATION_HORIZONS
    )
    family_current = []
    for family in CORE_FAMILIES:
        value = float(families.loc[latest_date, family])
        count = int(family_counts[family].loc[latest_date])
        family_current.append(
            {
                "family": family,
                "value": _json_value(value),
                "compositeContribution": _json_value(value / len(CORE_FAMILIES)),
                "signalCount": count,
                "signalTotal": int(signals[family].shape[1]),
            }
        )

    return {
        "meta": {
            "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
            "asOf": latest["date"],
            "definition": (
                "C5=国内政策流动性、信用传导和全球美元流动性等权形成的动态状态；"
                "NFCI仅作独立确认，不假设固定20个月周期。"
            ),
            "missingDataPolicy": "核心三层必须同时可用；平滑在缺失段重置，禁止跨缺失月份继承前值。",
        },
        "status": "state_direction_predictable" if core_qualified else "research_only",
        "publicationStatus": "limited",
        "current": {
            "date": latest["date"],
            "level": _json_value(latest["state"]),
            "slope3": _json_value(latest["slope3"]),
            "regime": latest["regime"],
            "familyDisagreement": _json_value(latest["familyDisagreement"]),
            "families": family_current,
            "coverageStatus": "full_three_layer_core",
        },
        "timeline": _records(timeline),
        "familyCoverage": [
            {
                "family": family,
                "start": _json_value(families[family].first_valid_index()),
                "end": _json_value(families[family].last_valid_index()),
                "observations": int(families[family].notna().sum()),
                "currentSignalCount": int(family_counts[family].loc[latest_date]),
                "signalTotal": int(signals[family].shape[1]),
            }
            for family in CORE_FAMILIES
        ],
        "signalCoverage": [
            {
                "family": family,
                "signal": signal,
                "start": _json_value(series.first_valid_index()),
                "end": _json_value(series.last_valid_index()),
                "observations": int(series.notna().sum()),
            }
            for family, family_signals in signals.items()
            for signal, series in family_signals.items()
        ],
        "confirmation": _confirmation_payload(state, confirmation),
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
        "ablationValidation": _ablation_validation(
            families,
            state,
            validations,
        ),
        "assetValidation": asset_validation,
        "governance": {
            "formalCycleStatus": "blocked",
            "stateStatus": "limited" if core_qualified else "blocked",
            "assetForecastStatus": asset_validation["status"],
            "notAllowed": [
                "固定20个月相位角",
                "把状态下行直接解释为资产下跌",
                "精确政策拐点日期",
                "未通过增量门槛的资产配置结论",
            ],
        },
        "caveat": (
            "三层状态的3至12个月方向可做研究提示；固定周期、精确政策拐点和资产收益风险预测仍按独立门槛管理。"
        ),
    }


def main() -> None:
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
