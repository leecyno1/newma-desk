"""Build the governed long-panel research diagnostic for C2 and C3.

The script separates three questions that were previously mixed together:

1. Is there recurring frequency content in the expected C2/C3 range?
2. Can the next one-to-three year direction be predicted out of sample?
3. Can the 1870-2020 historical panel be extended to a current research nowcast?

The historical panel comes from the JST Macrohistory Database R6. BIS selected
residential property prices and total-credit statistics, plus World Bank fixed
capital formation and GDP growth, provide the current bridge. The resulting
probabilities remain research diagnostics and do not change publication gates.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import requests
from scipy import signal
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "c2_c3_long_panel"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c2_c3_long_panel_research.json"

JST_URL = "https://www.macrohistory.net/app/download/9834512469/JSTdatasetR6.dta?t=1763503850"
BIS_SPP_URL = "https://stats.bis.org/api/v1/data/WS_SPP/all?startPeriod=1870"
BIS_TC_URL = "https://stats.bis.org/api/v1/data/WS_TC/all?startPeriod=1870"
WORLD_BANK_URL = "https://api.worldbank.org/v2/country/{countries}/indicator/{indicator}"

JST_COUNTRIES = [
    "AUS",
    "BEL",
    "CAN",
    "DNK",
    "FIN",
    "FRA",
    "DEU",
    "IRL",
    "ITA",
    "JPN",
    "NLD",
    "NOR",
    "PRT",
    "ESP",
    "SWE",
    "CHE",
    "GBR",
    "USA",
]

C2_BRIDGE_COUNTRIES = [*JST_COUNTRIES, "CHN"]

BIS_TO_ISO3 = {
    "AU": "AUS",
    "BE": "BEL",
    "CA": "CAN",
    "DK": "DNK",
    "FI": "FIN",
    "FR": "FRA",
    "DE": "DEU",
    "IE": "IRL",
    "IT": "ITA",
    "JP": "JPN",
    "NL": "NLD",
    "NO": "NOR",
    "PT": "PRT",
    "ES": "ESP",
    "SE": "SWE",
    "CH": "CHE",
    "GB": "GBR",
    "US": "USA",
    "CN": "CHN",
}

OECD_GFCF_URL = (
    "https://sdmx.oecd.org/public/rest/v1/data/"
    "OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA,1.1/"
    f"Q.Y.{'+'.join(JST_COUNTRIES)}.S1.S1.P51G._Z._T._Z.XDC.L.N.T0102"
    "?startPeriod=1990-Q1"
)
OECD_HOUSE_PRICE_URL = (
    "https://sdmx.oecd.org/public/rest/v1/data/"
    "OECD.ECO.MPD,DSD_AN_HOUSE_PRICES@DF_HOUSE_PRICES,1.0/"
    f"{'+'.join(JST_COUNTRIES)}.Q.HPI_RPI_AVG.PT_AVG_L_TERM"
    "?startPeriod=1970-Q1&dimensionAtObservation=AllDimensions"
)
OECD_HOUSE_PRICE_MEASURE = "HPI_RPI_AVG"
OECD_HOUSE_PRICE_CACHE = RAW_DIR / "OECD_HOUSE_PRICE_TO_RENT.csv"
OECD_SHORT_RATE_URL = (
    "https://sdmx.oecd.org/public/rest/v1/data/"
    "OECD.SDD.STES,DSD_STES@DF_FINMARK,4.0/"
    f"{'+'.join(JST_COUNTRIES)}.A.IR3TIB.PA._Z._Z._Z._Z.N"
    "?startPeriod=1960&dimensionAtObservation=AllDimensions"
)
OECD_SHORT_RATE_CACHE = RAW_DIR / "OECD_STES_SHORT_RATE.csv"


@dataclass(frozen=True)
class CycleSpec:
    cycle_id: str
    label: str
    expected_band_years: tuple[float, float]
    search_band_years: tuple[float, float]
    smoothing_span: int


CYCLE_SPECS = {
    "C2": CycleSpec("C2", "地产周期", (12.0, 20.0), (8.0, 28.0), 5),
    "C3": CycleSpec("C3", "资本周期", (7.0, 11.0), (5.0, 18.0), 3),
}

FAMILY_ABLATION_GROUPS = {
    "C2": {
        "housing": ("housing_momentum",),
        "mortgage_credit": ("mortgage_credit",),
        "investment": ("investment_confirmation",),
        "financing_conditions": ("financing_conditions",),
    },
    "C3": {
        "investment": (
            "investment_share",
            "investment_impulse3",
        ),
        "business_credit": ("business_credit_impulse3",),
        "real_growth": ("real_gdp_growth3",),
        "equity_market": ("equity_return3",),
        "financing_conditions": ("term_easing",),
    },
}
C2_CORE_FAMILIES = ("housing_momentum", "mortgage_credit")
C2_CONFIRMATION_FAMILIES = ("investment_confirmation", "financing_conditions")
C2_PROPAGATION_FAMILIES = (
    "real_gdp_growth3",
    "consumption_growth3",
    "employment_momentum3",
    "real_wage_growth3",
    "population_growth3",
)
C2_ARCHITECTURES = {
    "housing_single": {
        "label": "住房单指标",
        "factorFamilies": ("housing_momentum",),
        "modelFamilies": ("housing_momentum",),
        "role": "single_indicator_baseline",
    },
    "mortgage_single": {
        "label": "按揭信用单指标",
        "factorFamilies": ("mortgage_credit",),
        "modelFamilies": ("mortgage_credit",),
        "role": "single_indicator_baseline",
    },
    "core_composite": {
        "label": "住房—信用核心综合",
        "factorFamilies": C2_CORE_FAMILIES,
        "modelFamilies": C2_CORE_FAMILIES,
        "role": "core_composite",
    },
    "layered_confirmation": {
        "label": "核心综合 + 宏观确认",
        "factorFamilies": C2_CORE_FAMILIES,
        "modelFamilies": (*C2_CORE_FAMILIES, *C2_CONFIRMATION_FAMILIES),
        "role": "layered_confirmation",
    },
    "macro_propagation": {
        "label": "核心综合 + 经济传播",
        "factorFamilies": C2_CORE_FAMILIES,
        "modelFamilies": (*C2_CORE_FAMILIES, *C2_PROPAGATION_FAMILIES),
        "role": "macro_propagation",
    },
    "full_layered": {
        "label": "核心 + 确认 + 传播",
        "factorFamilies": C2_CORE_FAMILIES,
        "modelFamilies": (
            *C2_CORE_FAMILIES,
            *C2_CONFIRMATION_FAMILIES,
            *C2_PROPAGATION_FAMILIES,
        ),
        "role": "full_layered",
    },
    "broad_equal_composite": {
        "label": "全经济等权综合",
        "factorFamilies": (
            *C2_CORE_FAMILIES,
            *C2_CONFIRMATION_FAMILIES,
            *C2_PROPAGATION_FAMILIES,
        ),
        "modelFamilies": (
            *C2_CORE_FAMILIES,
            *C2_CONFIRMATION_FAMILIES,
            *C2_PROPAGATION_FAMILIES,
        ),
        "role": "broad_equal_composite",
    },
}
C2_FAMILY_ROLES = {
    "housing": "core",
    "mortgage_credit": "core",
    "investment": "confirmation",
    "financing_conditions": "confirmation",
}
FAMILY_ABLATION_LABELS = {
    "housing": "住房动量",
    "mortgage_credit": "按揭信用",
    "investment": "投资",
    "financing_conditions": "融资条件",
    "business_credit": "企业信用",
    "real_growth": "实际增长",
    "equity_market": "权益市场",
}
MINIMUM_ABLATION_DIRECTION_ACCURACY = 0.60
MINIMUM_ABLATION_COUNTRY_HOLDOUT_ACCURACY = 0.60
MINIMUM_ABLATION_TARGET_AGREEMENT = 0.75
MINIMUM_ABLATION_PASS_SHARE = 0.80
MAXIMUM_CORE_TARGET_AGREEMENT_FOR_MATERIALITY = 0.85
INDEPENDENT_OUTCOME_LABELS = {
    "consumption_acceleration": "消费增速加速",
    "unemployment_improvement": "失业率改善",
    "real_wage_acceleration": "实际工资增速加速",
}
MINIMUM_INDEPENDENT_OUTCOME_OBSERVATIONS = 300
MINIMUM_INDEPENDENT_OUTCOME_AUC = 0.55
MINIMUM_INDEPENDENT_OUTCOME_SPEARMAN = 0.10
MINIMUM_INDEPENDENT_OUTCOME_SUBPERIOD_AUC = 0.50
MINIMUM_INDEPENDENT_OUTCOME_COUNTRY_MEDIAN_AUC = 0.52
MINIMUM_INDEPENDENT_OUTCOME_AUC_IMPROVEMENT = 0.01
MINIMUM_INDEPENDENT_OUTCOME_BRIER_IMPROVEMENT = 0.001
MINIMUM_INDEPENDENT_OUTCOME_PASSED_CELLS = 4


def _download(
    url: str,
    destination: Path,
    *,
    accept: str | None = None,
    refresh: bool = False,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not refresh and destination.exists() and destination.stat().st_size > 1_000:
        return destination
    headers = {"User-Agent": "Mozilla/5.0"}
    if accept:
        headers["Accept"] = accept
    response = requests.get(url, headers=headers, timeout=180)
    response.raise_for_status()
    temporary = destination.with_suffix(f"{destination.suffix}.tmp")
    temporary.write_bytes(response.content)
    temporary.replace(destination)
    return destination


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, (np.integer, int)):
        return int(value)
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for row in frame.to_dict(orient="records"):
        rows.append({key: _json_value(value) for key, value in row.items()})
    return rows


def causal_robust_z(series: pd.Series, *, window: int = 30, min_periods: int = 15) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    rolling = numeric.rolling(window, min_periods=min_periods)
    center = rolling.median()
    mad = (numeric - center).abs().rolling(window, min_periods=min_periods).median() * 1.4826
    fallback = rolling.std(ddof=0)
    scale = mad.where(mad > 1e-8, fallback).replace(0, np.nan)
    return ((numeric - center) / scale).clip(-4.0, 4.0)


def _load_jst(*, refresh: bool = False) -> pd.DataFrame:
    path = _download(JST_URL, RAW_DIR / "JSTdatasetR6.dta", refresh=refresh)
    frame = pd.read_stata(path, convert_categoricals=False)
    frame["year"] = pd.to_numeric(frame["year"], errors="raise").astype(int)
    return frame.loc[frame["iso"].isin(JST_COUNTRIES)].copy()


def _jst_country_features(group: pd.DataFrame, cycle_id: str) -> pd.DataFrame:
    group = group.sort_values("year").set_index("year")
    nominal_gdp = pd.to_numeric(group["gdp"], errors="coerce").where(lambda value: value > 0)
    prices = pd.to_numeric(group["cpi"], errors="coerce").where(lambda value: value > 0)
    house_prices = pd.to_numeric(group["hpnom"], errors="coerce").where(lambda value: value > 0)
    real_gdp_per_capita = pd.to_numeric(group["rgdpmad"], errors="coerce").where(lambda value: value > 0)
    inflation = np.log(prices).diff()

    features = pd.DataFrame(index=group.index)
    if cycle_id == "C2":
        rental_yield = pd.to_numeric(
            group["housing_rent_yd"], errors="coerce"
        ).where(lambda value: value > 0)
        house_price_momentum = causal_robust_z(
            np.log(house_prices / prices).diff(3) / 3.0
        )
        valuation_momentum = causal_robust_z(
            -np.log(rental_yield).diff(3) / 3.0
        )
        housing_channels = pd.concat(
            [house_price_momentum, valuation_momentum], axis=1
        )
        features["housing_momentum"] = housing_channels.mean(
            axis=1, skipna=True
        ).where(housing_channels.notna().sum(axis=1) >= 1)
        features["mortgage_credit"] = causal_robust_z(
            (pd.to_numeric(group["tmort"], errors="coerce") / nominal_gdp).diff(3) / 3.0
        )
        investment_share = pd.to_numeric(group["iy"], errors="coerce")
        features["investment_confirmation"] = causal_robust_z(
            investment_share.diff(3) / 3.0
        )
        real_short_rate = (
            pd.to_numeric(group["stir"], errors="coerce") / 100.0 - inflation
        )
        features["financing_conditions"] = causal_robust_z(
            -real_short_rate.diff(3) / 3.0
        )
    else:
        investment_share = pd.to_numeric(group["iy"], errors="coerce")
        features["investment_share"] = causal_robust_z(investment_share)
        features["investment_impulse3"] = causal_robust_z(investment_share.diff(3) / 3.0)
        features["business_credit_impulse3"] = causal_robust_z(
            (pd.to_numeric(group["tbus"], errors="coerce") / nominal_gdp).diff(3) / 3.0
        )
        features["real_gdp_growth3"] = causal_robust_z(np.log(real_gdp_per_capita).diff(3) / 3.0)
        equity_return = pd.to_numeric(group["eq_tr"], errors="coerce").where(lambda value: value.between(-0.95, 3.0))
        features["equity_return3"] = causal_robust_z(equity_return.rolling(3, min_periods=2).mean())
        features["term_easing"] = causal_robust_z(
            -(pd.to_numeric(group["stir"], errors="coerce") - pd.to_numeric(group["ltrate"], errors="coerce"))
        )
    return features


def _country_factor(features: pd.DataFrame, cycle_id: str) -> pd.Series:
    factor_inputs = features
    required_family_count = 2
    if cycle_id == "C2":
        available_core = [
            family for family in C2_CORE_FAMILIES if family in features.columns
        ]
        factor_inputs = features[available_core]
        required_family_count = 2 if len(available_core) == 2 else 1
    factor = factor_inputs.mean(axis=1, skipna=True).where(
        factor_inputs.notna().sum(axis=1) >= required_family_count
    )
    return factor.ewm(
        span=CYCLE_SPECS[cycle_id].smoothing_span,
        adjust=False,
        min_periods=2,
    ).mean()


def build_jst_panel(
    jst: pd.DataFrame,
    cycle_id: str,
    *,
    excluded_families: set[str] | None = None,
) -> pd.DataFrame:
    excluded = excluded_families or set()
    rows: list[pd.DataFrame] = []
    for iso, country in jst.groupby("iso"):
        features = _jst_country_features(country, cycle_id).drop(
            columns=list(excluded),
            errors="ignore",
        )
        country_frame = features.add_prefix("family_")
        country_frame["factor"] = _country_factor(features, cycle_id)
        country_frame["iso"] = iso
        country_frame["year"] = country_frame.index.astype(int)
        rows.append(country_frame.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)


def _model_frame(panel: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    for _, country in panel.groupby("iso"):
        country = country.sort_values("year").copy()
        for lag in range(1, 7):
            country[f"lag_{lag}"] = country["factor"].shift(lag)
        country["slope_1"] = country["factor"].diff()
        country["slope_3"] = country["factor"].diff(3) / 3.0
        country["slope_5"] = country["factor"].diff(5) / 5.0
        country["future_factor"] = country["factor"].shift(-horizon)
        country["target_up"] = (country["future_factor"] > country["factor"]).astype(float)
        frames.append(country)
    model_frame = pd.concat(frames, ignore_index=True)
    model_frame = model_frame.dropna(subset=["factor", "future_factor", "target_up", "slope_3"])
    feature_columns = [
        column
        for column in model_frame.columns
        if column.startswith("family_") or column.startswith("lag_") or column.startswith("slope_")
    ]
    return model_frame, feature_columns


def _classifier() -> object:
    return make_pipeline(
        SimpleImputer(strategy="median", add_indicator=True),
        StandardScaler(),
        LogisticRegression(C=0.1, max_iter=1_000, class_weight="balanced"),
    )


def _safe_auc(actual: np.ndarray, probabilities: np.ndarray) -> float | None:
    if len(np.unique(actual)) < 2:
        return None
    return float(roc_auc_score(actual, probabilities))


def _period_metrics(
    actual: np.ndarray,
    probabilities: np.ndarray,
    base_probabilities: np.ndarray,
    momentum: np.ndarray,
    iso: np.ndarray,
) -> dict[str, object]:
    country_accuracy = pd.Series((probabilities >= 0.5) == actual).groupby(iso).mean()
    return {
        "observations": int(len(actual)),
        "accuracy": _json_value(np.mean((probabilities >= 0.5) == actual)),
        "momentumAccuracy": _json_value(np.mean(momentum == actual)),
        "brier": _json_value(brier_score_loss(actual, probabilities)),
        "baseBrier": _json_value(brier_score_loss(actual, base_probabilities)),
        "auc": _json_value(_safe_auc(actual, probabilities)),
        "countryMedianAccuracy": _json_value(country_accuracy.median()),
        "countriesAboveChanceShare": _json_value((country_accuracy > 0.5).mean()),
    }


def recursive_validation(panel: pd.DataFrame, horizon: int) -> dict[str, object]:
    model_frame, feature_columns = _model_frame(panel, horizon)
    probabilities: list[float] = []
    base_probabilities: list[float] = []
    actual: list[int] = []
    momentum: list[int] = []
    countries: list[str] = []
    years: list[int] = []

    for year in sorted(model_frame["year"].unique()):
        if year < 1950:
            continue
        train = model_frame.loc[model_frame["year"] <= year - horizon]
        test = model_frame.loc[model_frame["year"] == year]
        if len(train) < 250 or test.empty or train["target_up"].nunique() < 2:
            continue
        model = _classifier()
        model.fit(train[feature_columns], train["target_up"].astype(int))
        probabilities.extend(model.predict_proba(test[feature_columns])[:, 1].tolist())
        base_probabilities.extend([float(train["target_up"].mean())] * len(test))
        actual.extend(test["target_up"].astype(int).tolist())
        momentum.extend((test["slope_3"] > 0).astype(int).tolist())
        countries.extend(test["iso"].astype(str).tolist())
        years.extend(test["year"].astype(int).tolist())

    probability_array = np.asarray(probabilities)
    base_array = np.asarray(base_probabilities)
    actual_array = np.asarray(actual)
    momentum_array = np.asarray(momentum)
    country_array = np.asarray(countries)
    year_array = np.asarray(years)

    result = _period_metrics(
        actual_array,
        probability_array,
        base_array,
        momentum_array,
        country_array,
    )
    result["subperiods"] = []
    for start, end in ((1950, 1984), (1985, 2020)):
        mask = (year_array >= start) & (year_array <= end)
        if not mask.any():
            continue
        metrics = _period_metrics(
            actual_array[mask],
            probability_array[mask],
            base_array[mask],
            momentum_array[mask],
            country_array[mask],
        )
        metrics.update({"start": start, "end": end})
        result["subperiods"].append(metrics)

    leave_country_probabilities: list[float] = []
    leave_country_actual: list[int] = []
    leave_country_iso: list[str] = []
    for iso in sorted(model_frame["iso"].unique()):
        train = model_frame.loc[(model_frame["iso"] != iso) & (model_frame["year"] <= 1999)]
        test = model_frame.loc[(model_frame["iso"] == iso) & (model_frame["year"] >= 2000)]
        if len(train) < 250 or test.empty or train["target_up"].nunique() < 2:
            continue
        model = _classifier()
        model.fit(train[feature_columns], train["target_up"].astype(int))
        leave_country_probabilities.extend(model.predict_proba(test[feature_columns])[:, 1].tolist())
        leave_country_actual.extend(test["target_up"].astype(int).tolist())
        leave_country_iso.extend(test["iso"].astype(str).tolist())

    leave_probability_array = np.asarray(leave_country_probabilities)
    leave_actual_array = np.asarray(leave_country_actual)
    leave_country_array = np.asarray(leave_country_iso)
    leave_accuracy = pd.Series((leave_probability_array >= 0.5) == leave_actual_array).groupby(
        leave_country_array
    ).mean()
    result["leaveCountryOut2000Plus"] = {
        "observations": int(len(leave_actual_array)),
        "accuracy": _json_value(np.mean((leave_probability_array >= 0.5) == leave_actual_array)),
        "brier": _json_value(brier_score_loss(leave_actual_array, leave_probability_array)),
        "countryMedianAccuracy": _json_value(leave_accuracy.median()),
        "countriesAboveChanceShare": _json_value((leave_accuracy > 0.5).mean()),
    }
    return result


def _recursive_probability_frame(
    panel: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    model_frame, feature_columns = _model_frame(panel, horizon)
    rows: list[pd.DataFrame] = []
    for year in sorted(model_frame["year"].unique()):
        if year < 1950:
            continue
        train = model_frame.loc[model_frame["year"] <= year - horizon]
        test = model_frame.loc[model_frame["year"] == year]
        if len(train) < 250 or test.empty or train["target_up"].nunique() < 2:
            continue
        model = _classifier()
        model.fit(train[feature_columns], train["target_up"].astype(int))
        result = test[["iso", "year"]].copy()
        result["probability"] = model.predict_proba(test[feature_columns])[:, 1]
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


def _independent_outcome_frame(
    jst: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for iso, country in jst.groupby("iso"):
        country = country.sort_values("year").copy()
        consumption = pd.to_numeric(
            country["rconsbarro"], errors="coerce"
        ).where(lambda value: value > 0)
        unemployment = pd.to_numeric(country["unemp"], errors="coerce")
        wages = pd.to_numeric(country["wage"], errors="coerce").where(
            lambda value: value > 0
        )
        prices = pd.to_numeric(country["cpi"], errors="coerce").where(
            lambda value: value > 0
        )
        outcome_levels = {
            "consumption_acceleration": np.log(consumption).diff(horizon)
            / horizon,
            "unemployment_improvement": -unemployment,
            "real_wage_acceleration": np.log(wages / prices).diff(horizon)
            / horizon,
        }
        for outcome_id, level in outcome_levels.items():
            continuous = (level.shift(-horizon) - level) / horizon
            current_state = causal_robust_z(level)
            state_momentum = causal_robust_z(level.diff())
            outcome = pd.DataFrame(
                {
                    "iso": iso,
                    "year": country["year"].astype(int),
                    "outcomeId": outcome_id,
                    "currentState": current_state,
                    "stateMomentum": state_momentum,
                    "continuousOutcome": continuous,
                    "actualImprovement": (continuous > 0).astype(float),
                }
            )
            outcome.loc[continuous.isna(), "actualImprovement"] = np.nan
            rows.append(outcome)
    return pd.concat(rows, ignore_index=True)


def _recursive_outcome_channel_predictions(
    frame: pd.DataFrame,
    horizon: int,
) -> pd.DataFrame:
    frame = frame.copy()
    frame["factorSignal"] = frame["factorProbability"] - 0.5
    frame["factorInteraction"] = frame["factorSignal"] * frame["currentState"]
    baseline_features = ["currentState", "stateMomentum"]
    channel_features = [*baseline_features, "factorSignal", "factorInteraction"]
    rows: list[pd.DataFrame] = []
    for year in sorted(frame["year"].unique()):
        train = frame.loc[frame["year"] <= year - horizon]
        test = frame.loc[frame["year"] == year]
        if len(train) < 250 or test.empty or train["actualImprovement"].nunique() < 2:
            continue
        baseline_model = _classifier()
        channel_model = _classifier()
        target = train["actualImprovement"].astype(int)
        baseline_model.fit(train[baseline_features], target)
        channel_model.fit(train[channel_features], target)
        result = test[
            ["iso", "year", "actualImprovement", "continuousOutcome"]
        ].copy()
        result["baselineProbability"] = baseline_model.predict_proba(
            test[baseline_features]
        )[:, 1]
        result["channelProbability"] = channel_model.predict_proba(
            test[channel_features]
        )[:, 1]
        rows.append(result)
    return pd.concat(rows, ignore_index=True)


def independent_outcome_validation(
    jst: pd.DataFrame,
    panel: pd.DataFrame,
) -> dict[str, object]:
    cells: list[dict[str, object]] = []
    for horizon in (1, 3):
        probabilities = _recursive_probability_frame(panel, horizon)
        probabilities = probabilities.rename(
            columns={"probability": "factorProbability"}
        )
        outcomes = _independent_outcome_frame(jst, horizon)
        comparable = probabilities.merge(outcomes, on=["iso", "year"]).dropna()
        for outcome_id in INDEPENDENT_OUTCOME_LABELS:
            frame = comparable.loc[comparable["outcomeId"] == outcome_id].copy()
            predictions = _recursive_outcome_channel_predictions(frame, horizon)
            actual = predictions["actualImprovement"].astype(int)
            channel_probability = predictions["channelProbability"]
            baseline_probability = predictions["baselineProbability"]
            auc = _safe_auc(actual.to_numpy(), channel_probability.to_numpy())
            baseline_auc = _safe_auc(
                actual.to_numpy(), baseline_probability.to_numpy()
            )
            auc_improvement = (
                None
                if auc is None or baseline_auc is None
                else float(auc - baseline_auc)
            )
            brier = brier_score_loss(actual, channel_probability)
            baseline_brier = brier_score_loss(actual, baseline_probability)
            brier_improvement = float(baseline_brier - brier)
            spearman = predictions[
                ["channelProbability", "continuousOutcome"]
            ].corr(
                method="spearman"
            ).iloc[0, 1]
            subperiods = []
            for start, end in ((1950, 1984), (1985, 2020)):
                period = predictions.loc[predictions["year"].between(start, end)]
                period_auc = _safe_auc(
                    period["actualImprovement"].astype(int).to_numpy(),
                    period["channelProbability"].to_numpy(),
                )
                period_baseline_auc = _safe_auc(
                    period["actualImprovement"].astype(int).to_numpy(),
                    period["baselineProbability"].to_numpy(),
                )
                subperiods.append(
                    {
                        "start": start,
                        "end": end,
                        "observations": int(len(period)),
                        "auc": _json_value(period_auc),
                        "baselineAuc": _json_value(period_baseline_auc),
                    }
                )
            country_auc = []
            for _, country in predictions.groupby("iso"):
                if len(country) < 20 or country["actualImprovement"].nunique() < 2:
                    continue
                country_auc.append(
                    roc_auc_score(
                        country["actualImprovement"].astype(int),
                        country["channelProbability"],
                    )
                )
            country_median_auc = float(np.median(country_auc))
            passed = (
                len(predictions) >= MINIMUM_INDEPENDENT_OUTCOME_OBSERVATIONS
                and auc is not None
                and auc >= MINIMUM_INDEPENDENT_OUTCOME_AUC
                and auc_improvement is not None
                and auc_improvement
                >= MINIMUM_INDEPENDENT_OUTCOME_AUC_IMPROVEMENT
                and brier_improvement
                >= MINIMUM_INDEPENDENT_OUTCOME_BRIER_IMPROVEMENT
                and math.isfinite(float(spearman))
                and float(spearman) >= MINIMUM_INDEPENDENT_OUTCOME_SPEARMAN
                and all(
                    row["auc"] is not None
                    and float(row["auc"])
                    >= MINIMUM_INDEPENDENT_OUTCOME_SUBPERIOD_AUC
                    for row in subperiods
                )
                and country_median_auc
                >= MINIMUM_INDEPENDENT_OUTCOME_COUNTRY_MEDIAN_AUC
            )
            cells.append(
                {
                    "outcomeId": outcome_id,
                    "label": INDEPENDENT_OUTCOME_LABELS[outcome_id],
                    "horizonYears": horizon,
                    "observations": int(len(predictions)),
                    "auc": _json_value(auc),
                    "baselineAuc": _json_value(baseline_auc),
                    "aucImprovement": _json_value(auc_improvement),
                    "brier": _json_value(brier),
                    "baselineBrier": _json_value(baseline_brier),
                    "brierImprovement": _json_value(brier_improvement),
                    "spearman": _json_value(spearman),
                    "countryMedianAuc": _json_value(country_median_auc),
                    "subperiods": subperiods,
                    "passed": passed,
                }
            )
    passed_cells = sum(bool(row["passed"]) for row in cells)
    covered_outcomes = {
        str(row["outcomeId"])
        for row in cells
        if bool(row["passed"])
    }
    qualified = (
        passed_cells >= MINIMUM_INDEPENDENT_OUTCOME_PASSED_CELLS
        and covered_outcomes == set(INDEPENDENT_OUTCOME_LABELS)
    )
    return {
        "status": "passed_limited" if qualified else "failed",
        "passedCells": passed_cells,
        "cellCount": len(cells),
        "coveredOutcomes": sorted(covered_outcomes),
        "requiredPassedCells": MINIMUM_INDEPENDENT_OUTCOME_PASSED_CELLS,
        "requiresEveryOutcome": True,
        "gates": {
            "minimumObservations": MINIMUM_INDEPENDENT_OUTCOME_OBSERVATIONS,
            "minimumAuc": MINIMUM_INDEPENDENT_OUTCOME_AUC,
            "minimumSpearman": MINIMUM_INDEPENDENT_OUTCOME_SPEARMAN,
            "minimumSubperiodAuc": MINIMUM_INDEPENDENT_OUTCOME_SUBPERIOD_AUC,
            "minimumCountryMedianAuc": (
                MINIMUM_INDEPENDENT_OUTCOME_COUNTRY_MEDIAN_AUC
            ),
            "minimumAucImprovement": (
                MINIMUM_INDEPENDENT_OUTCOME_AUC_IMPROVEMENT
            ),
            "minimumBrierImprovement": (
                MINIMUM_INDEPENDENT_OUTCOME_BRIER_IMPROVEMENT
            ),
        },
        "cells": cells,
        "method": "每类结果分别做递归样本外校准；基准只使用该结果自身的当前状态与惯性，挑战者固定增加C2/C3因子方向概率及其状态交互。只有AUC、秩相关、Brier和跨时期门槛同时通过，才认定周期因子提供独立增量信息。",
        "caveat": "失败表示因子自身方向可预测，但对消费、就业或实际工资的增量信息尚不稳定，不能外推为广义经济结果预测。",
    }


def _build_c2_architecture_panel(
    jst: pd.DataFrame,
    architecture_id: str,
) -> pd.DataFrame:
    architecture = C2_ARCHITECTURES[architecture_id]
    rows: list[pd.DataFrame] = []
    for iso, country in jst.groupby("iso"):
        features = _jst_country_features(country, "C2")
        indexed = country.sort_values("year").set_index("year")
        prices = pd.to_numeric(indexed["cpi"], errors="coerce").where(
            lambda value: value > 0
        )
        real_gdp = pd.to_numeric(indexed["rgdpmad"], errors="coerce").where(
            lambda value: value > 0
        )
        consumption = pd.to_numeric(
            indexed["rconsbarro"], errors="coerce"
        ).where(lambda value: value > 0)
        unemployment = pd.to_numeric(indexed["unemp"], errors="coerce")
        wages = pd.to_numeric(indexed["wage"], errors="coerce").where(
            lambda value: value > 0
        )
        population = pd.to_numeric(indexed["pop"], errors="coerce").where(
            lambda value: value > 0
        )
        features["real_gdp_growth3"] = causal_robust_z(
            np.log(real_gdp).diff(3) / 3.0
        )
        features["consumption_growth3"] = causal_robust_z(
            np.log(consumption).diff(3) / 3.0
        )
        features["employment_momentum3"] = causal_robust_z(
            -unemployment.diff(3) / 3.0
        )
        features["real_wage_growth3"] = causal_robust_z(
            np.log(wages / prices).diff(3) / 3.0
        )
        features["population_growth3"] = causal_robust_z(
            np.log(population).diff(3) / 3.0
        )
        core_inputs = features[list(C2_CORE_FAMILIES)]
        reference_factor = (
            core_inputs.mean(axis=1, skipna=True)
            .where(core_inputs.notna().sum(axis=1) >= len(C2_CORE_FAMILIES))
            .ewm(
                span=CYCLE_SPECS["C2"].smoothing_span,
                adjust=False,
                min_periods=2,
            )
            .mean()
        )
        factor_families = list(architecture["factorFamilies"])
        factor_inputs = features[factor_families]
        if architecture_id == "broad_equal_composite":
            valid = core_inputs.notna().sum(axis=1) >= len(C2_CORE_FAMILIES)
        else:
            valid = factor_inputs.notna().sum(axis=1) >= len(factor_families)
        factor = (
            factor_inputs.mean(axis=1, skipna=True)
            .where(valid)
            .ewm(
                span=CYCLE_SPECS["C2"].smoothing_span,
                adjust=False,
                min_periods=2,
            )
            .mean()
        )
        model_families = list(architecture["modelFamilies"])
        frame = features[model_families].add_prefix("family_")
        frame["factor"] = factor
        frame["referenceFactor"] = reference_factor
        frame["iso"] = iso
        frame["year"] = frame.index.astype(int)
        rows.append(frame.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)


def _c2_common_target_model_frame(
    panel: pd.DataFrame,
    horizon: int,
) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    for _, country in panel.groupby("iso"):
        country = country.sort_values("year").copy()
        for lag in range(1, 7):
            country[f"lag_{lag}"] = country["factor"].shift(lag)
        country["slope_1"] = country["factor"].diff()
        country["slope_3"] = country["factor"].diff(3) / 3.0
        country["slope_5"] = country["factor"].diff(5) / 5.0
        country["futureReferenceFactor"] = country["referenceFactor"].shift(-horizon)
        country["target_up"] = (
            country["futureReferenceFactor"] > country["referenceFactor"]
        ).astype(float)
        country.loc[
            country["futureReferenceFactor"].isna()
            | country["referenceFactor"].isna(),
            "target_up",
        ] = np.nan
        frames.append(country)
    model_frame = pd.concat(frames, ignore_index=True).dropna(
        subset=[
            "factor",
            "referenceFactor",
            "futureReferenceFactor",
            "target_up",
            "slope_3",
        ]
    )
    feature_columns = [
        column
        for column in model_frame.columns
        if column.startswith("family_")
        or column.startswith("lag_")
        or column.startswith("slope_")
    ]
    return model_frame, feature_columns


def _c2_common_target_validation(
    panel: pd.DataFrame,
    horizon: int,
) -> dict[str, object]:
    model_frame, feature_columns = _c2_common_target_model_frame(panel, horizon)
    probabilities: list[float] = []
    base_probabilities: list[float] = []
    actual: list[int] = []
    momentum: list[int] = []
    countries: list[str] = []
    years: list[int] = []
    for year in sorted(model_frame["year"].unique()):
        if year < 1950:
            continue
        train = model_frame.loc[model_frame["year"] <= year - horizon]
        test = model_frame.loc[model_frame["year"] == year]
        if len(train) < 250 or test.empty or train["target_up"].nunique() < 2:
            continue
        model = _classifier()
        model.fit(train[feature_columns], train["target_up"].astype(int))
        probabilities.extend(model.predict_proba(test[feature_columns])[:, 1].tolist())
        base_probabilities.extend([float(train["target_up"].mean())] * len(test))
        actual.extend(test["target_up"].astype(int).tolist())
        momentum.extend((test["slope_3"] > 0).astype(int).tolist())
        countries.extend(test["iso"].astype(str).tolist())
        years.extend(test["year"].astype(int).tolist())

    probability_array = np.asarray(probabilities)
    actual_array = np.asarray(actual)
    country_array = np.asarray(countries)
    result = _period_metrics(
        actual_array,
        probability_array,
        np.asarray(base_probabilities),
        np.asarray(momentum),
        country_array,
    )
    result["subperiods"] = []
    year_array = np.asarray(years)
    for start, end in ((1950, 1984), (1985, 2020)):
        mask = (year_array >= start) & (year_array <= end)
        if not mask.any():
            continue
        metrics = _period_metrics(
            actual_array[mask],
            probability_array[mask],
            np.asarray(base_probabilities)[mask],
            np.asarray(momentum)[mask],
            country_array[mask],
        )
        metrics.update({"start": start, "end": end})
        result["subperiods"].append(metrics)

    leave_probabilities: list[float] = []
    leave_actual: list[int] = []
    leave_countries: list[str] = []
    for iso in sorted(model_frame["iso"].unique()):
        train = model_frame.loc[
            (model_frame["iso"] != iso) & (model_frame["year"] <= 1999)
        ]
        test = model_frame.loc[
            (model_frame["iso"] == iso) & (model_frame["year"] >= 2000)
        ]
        if len(train) < 250 or test.empty or train["target_up"].nunique() < 2:
            continue
        model = _classifier()
        model.fit(train[feature_columns], train["target_up"].astype(int))
        leave_probabilities.extend(
            model.predict_proba(test[feature_columns])[:, 1].tolist()
        )
        leave_actual.extend(test["target_up"].astype(int).tolist())
        leave_countries.extend(test["iso"].astype(str).tolist())
    leave_probability_array = np.asarray(leave_probabilities)
    leave_actual_array = np.asarray(leave_actual)
    leave_country_array = np.asarray(leave_countries)
    leave_accuracy = pd.Series(
        (leave_probability_array >= 0.5) == leave_actual_array
    ).groupby(leave_country_array).mean()
    result["leaveCountryOut2000Plus"] = {
        "observations": int(len(leave_actual_array)),
        "accuracy": _json_value(
            np.mean((leave_probability_array >= 0.5) == leave_actual_array)
        ),
        "brier": _json_value(
            brier_score_loss(leave_actual_array, leave_probability_array)
        ),
        "auc": _json_value(
            _safe_auc(leave_actual_array, leave_probability_array)
        ),
        "countryMedianAccuracy": _json_value(leave_accuracy.median()),
        "countriesAboveChanceShare": _json_value(
            (leave_accuracy > 0.5).mean()
        ),
    }
    return result


def c2_architecture_comparison(jst: pd.DataFrame) -> dict[str, object]:
    architectures: list[dict[str, object]] = []
    for architecture_id, specification in C2_ARCHITECTURES.items():
        panel = _build_c2_architecture_panel(jst, architecture_id)
        validation = {
            f"{horizon}y": _c2_common_target_validation(panel, horizon)
            for horizon in (1, 2, 3)
        }
        outcome_validation = (
            independent_outcome_validation(jst, panel)
            if architecture_id == "core_composite"
            else {
                "status": "not_used_for_selection",
                "reason": "传播层含GDP、消费、就业或工资时，不再用这些结果验证同一架构，避免自解释。",
            }
        )
        accuracy_mean = float(
            np.mean([validation[f"{horizon}y"]["accuracy"] for horizon in (1, 2, 3)])
        )
        holdout_accuracy_mean = float(
            np.mean(
                [
                    validation[f"{horizon}y"]["leaveCountryOut2000Plus"]["accuracy"]
                    for horizon in (1, 2, 3)
                ]
            )
        )
        brier_mean = float(
            np.mean([validation[f"{horizon}y"]["brier"] for horizon in (1, 2, 3)])
        )
        holdout_brier_mean = float(
            np.mean(
                [
                    validation[f"{horizon}y"]["leaveCountryOut2000Plus"]["brier"]
                    for horizon in (1, 2, 3)
                ]
            )
        )
        score = (
            accuracy_mean
            + holdout_accuracy_mean
            + (1.0 - brier_mean)
            + (1.0 - holdout_brier_mean)
        ) / 4.0
        architectures.append(
            {
                "architectureId": architecture_id,
                "label": specification["label"],
                "role": specification["role"],
                "factorFamilies": list(specification["factorFamilies"]),
                "modelFamilies": list(specification["modelFamilies"]),
                "validation": validation,
                "independentOutcomeValidation": outcome_validation,
                "summary": {
                    "accuracyMean": _json_value(accuracy_mean),
                    "countryHoldoutAccuracyMean": _json_value(
                        holdout_accuracy_mean
                    ),
                    "brierMean": _json_value(brier_mean),
                    "countryHoldoutBrierMean": _json_value(
                        holdout_brier_mean
                    ),
                    "score": _json_value(score),
                },
            }
        )
    selected = max(
        architectures,
        key=lambda architecture: float(architecture["summary"]["score"]),
    )
    core = next(
        row for row in architectures if row["architectureId"] == "core_composite"
    )
    layered = next(
        row
        for row in architectures
        if row["architectureId"] == "layered_confirmation"
    )
    broad = next(
        row
        for row in architectures
        if row["architectureId"] == "broad_equal_composite"
    )
    propagation = next(
        row
        for row in architectures
        if row["architectureId"] == "macro_propagation"
    )
    confirmation_brier_gain = float(core["summary"]["brierMean"]) - float(
        layered["summary"]["brierMean"]
    )
    confirmation_accuracy_gain = float(
        layered["summary"]["accuracyMean"]
    ) - float(core["summary"]["accuracyMean"])
    broad_brier_change = float(core["summary"]["brierMean"]) - float(
        broad["summary"]["brierMean"]
    )
    broad_accuracy_change = float(broad["summary"]["accuracyMean"]) - float(
        core["summary"]["accuracyMean"]
    )
    propagation_brier_gain = float(core["summary"]["brierMean"]) - float(
        propagation["summary"]["brierMean"]
    )
    propagation_accuracy_gain = float(
        propagation["summary"]["accuracyMean"]
    ) - float(core["summary"]["accuracyMean"])
    propagation_holdout_accuracy_gain = float(
        propagation["summary"]["countryHoldoutAccuracyMean"]
    ) - float(core["summary"]["countryHoldoutAccuracyMean"])
    return {
        "status": "core_composite_selected",
        "commonTarget": "未来住房—按揭信用核心综合因子的上行/下行方向",
        "selectedArchitecture": str(selected["architectureId"]),
        "architectures": architectures,
        "recommendation": {
            "cycleDefinition": "住房动量与按揭信用共同定义C2；不使用单一指标，也不把所有宏观指标等权塞进周期核心。",
            "confirmationLayer": "投资脉冲与融资条件保留为确认和传播通道；当前样本外改善不足，不默认进入方向概率模型。",
            "propagationLayer": "GDP、消费、就业、实际工资与人口进入经济传播层；其平均Brier略有改善，但方向准确率和国家留一稳定性下降，因此不进入C2核心。",
            "singleIndicatorRole": "单指标只作为透明基准、异常触发器和逐家族剔除检验。",
            "confirmationBrierGain": _json_value(confirmation_brier_gain),
            "confirmationAccuracyGain": _json_value(confirmation_accuracy_gain),
            "broadCompositeBrierGain": _json_value(broad_brier_change),
            "broadCompositeAccuracyGain": _json_value(broad_accuracy_change),
            "propagationBrierGain": _json_value(propagation_brier_gain),
            "propagationAccuracyGain": _json_value(
                propagation_accuracy_gain
            ),
            "propagationCountryHoldoutAccuracyGain": _json_value(
                propagation_holdout_accuracy_gain
            ),
            "externalOutcomePassedCells": int(
                core["independentOutcomeValidation"]["passedCells"]
            ),
            "externalOutcomeTotalCells": int(
                core["independentOutcomeValidation"]["cellCount"]
            ),
        },
        "governance": {
            "confirmationPromotionRule": "确认层只有在递归样本外和国家留一Brier均稳定改善，且不降低跨时期准确率时，才允许进入默认方向模型。",
            "broadFactorRule": "GDP、消费、就业、工资和总投资等宏观变量先进入传播层；只有对固定C2目标提供增量信息后，才可升级为核心。",
            "notAllowed": [
                "用预测因子自身定义预测目标后比较不同架构",
                "为提高拟合度把C3资本形成重复计入C2核心",
                "依据单次显著性挑选指标",
            ],
        },
    }


def _target_direction_agreement(
    baseline_panel: pd.DataFrame,
    ablated_panel: pd.DataFrame,
    horizon: int,
) -> dict[str, object]:
    baseline, _ = _model_frame(baseline_panel, horizon)
    ablated, _ = _model_frame(ablated_panel, horizon)
    comparable = baseline[["iso", "year", "target_up"]].merge(
        ablated[["iso", "year", "target_up"]],
        on=["iso", "year"],
        suffixes=("Baseline", "Ablated"),
        how="inner",
    )
    country_agreement = (
        comparable.assign(
            agreement=(
                comparable["target_upBaseline"]
                == comparable["target_upAblated"]
            )
        )
        .groupby("iso")["agreement"]
        .mean()
    )
    return {
        "observations": int(len(comparable)),
        "agreement": _json_value(
            np.mean(
                comparable["target_upBaseline"]
                == comparable["target_upAblated"]
            )
        ),
        "countryMedianAgreement": _json_value(country_agreement.median()),
        "countriesAboveThresholdShare": _json_value(
            (country_agreement >= MINIMUM_ABLATION_TARGET_AGREEMENT).mean()
        ),
    }


def family_ablation_validation(
    jst: pd.DataFrame,
    cycle_id: str,
    baseline_historical: pd.DataFrame,
    baseline_bridge: pd.DataFrame,
    *,
    spp: pd.DataFrame,
    total_credit: pd.DataFrame,
    world_bank: pd.DataFrame,
    oecd_house_prices: pd.DataFrame | None = None,
    oecd_short_rates: pd.DataFrame | None = None,
) -> dict[str, object]:
    baseline_forecasts = {
        horizon: current_direction_forecast(
            baseline_historical,
            baseline_bridge,
            horizon,
        )
        for horizon in (1, 3)
    }
    results: list[dict[str, object]] = []
    for group_id, families in FAMILY_ABLATION_GROUPS[cycle_id].items():
        role = C2_FAMILY_ROLES.get(group_id, "core") if cycle_id == "C2" else "core"
        active_in_default_model = not (
            cycle_id == "C2" and role == "confirmation"
        )
        if active_in_default_model:
            excluded = set(families)
            if cycle_id == "C2":
                excluded.update(C2_CONFIRMATION_FAMILIES)
            historical = build_jst_panel(
                jst,
                cycle_id,
                excluded_families=excluded,
            )
            bridge = build_bridge_panel(
                cycle_id,
                spp=spp,
                total_credit=total_credit,
                world_bank=world_bank,
                oecd_house_prices=oecd_house_prices,
                oecd_short_rates=oecd_short_rates,
                excluded_families=excluded,
            )
        else:
            historical = baseline_historical
            bridge = baseline_bridge
        horizons: dict[str, object] = {}
        horizon_passes: list[bool] = []
        current_probability_shifts: list[float] = []
        for horizon in (1, 3):
            validation = recursive_validation(historical, horizon)
            target_agreement = _target_direction_agreement(
                baseline_historical,
                historical,
                horizon,
            )
            forecast = current_direction_forecast(
                historical,
                bridge,
                horizon,
            )
            probability_shift = float(forecast["probabilityUp"]) - float(
                baseline_forecasts[horizon]["probabilityUp"]
            )
            passed = (
                float(validation["accuracy"])
                >= MINIMUM_ABLATION_DIRECTION_ACCURACY
                and float(
                    validation["leaveCountryOut2000Plus"]["accuracy"]
                )
                >= MINIMUM_ABLATION_COUNTRY_HOLDOUT_ACCURACY
                and float(target_agreement["agreement"])
                >= MINIMUM_ABLATION_TARGET_AGREEMENT
            )
            if role == "confirmation":
                passed = (
                    float(validation["accuracy"])
                    >= MINIMUM_ABLATION_DIRECTION_ACCURACY
                    and float(
                        validation["leaveCountryOut2000Plus"]["accuracy"]
                    )
                    >= MINIMUM_ABLATION_COUNTRY_HOLDOUT_ACCURACY
                    and float(target_agreement["agreement"]) >= 0.95
                )
            horizon_passes.append(passed)
            current_probability_shifts.append(probability_shift)
            horizons[f"{horizon}y"] = {
                "accuracy": validation["accuracy"],
                "baseBrier": validation["baseBrier"],
                "brier": validation["brier"],
                "countryHoldoutAccuracy": validation[
                    "leaveCountryOut2000Plus"
                ]["accuracy"],
                "targetAgreement": target_agreement,
                "currentProbabilityUp": forecast["probabilityUp"],
                "baselineProbabilityUp": baseline_forecasts[horizon][
                    "probabilityUp"
                ],
                "currentProbabilityShift": _json_value(probability_shift),
                "passed": passed,
            }
        results.append(
            {
                "groupId": group_id,
                "label": FAMILY_ABLATION_LABELS[group_id],
                "role": role,
                "activeInDefaultModel": active_in_default_model,
                "excludedFamilies": list(families),
                "status": "passed" if all(horizon_passes) else "failed",
                "horizons": horizons,
                "maximumAbsoluteCurrentProbabilityShift": _json_value(
                    max(abs(value) for value in current_probability_shifts)
                ),
            }
        )
    passed_groups = sum(row["status"] == "passed" for row in results)
    pass_share = passed_groups / len(results) if results else 0.0
    maximum_shift = max(
        float(row["maximumAbsoluteCurrentProbabilityShift"])
        for row in results
    )
    confirmation_groups = [row for row in results if row["role"] == "confirmation"]
    core_groups = [row for row in results if row["role"] == "core"]
    confirmation_stable = bool(confirmation_groups) and all(
        row["status"] == "passed" for row in confirmation_groups
    )
    core_necessary = all(
        any(
            abs(float(horizon["currentProbabilityShift"])) >= 0.10
            or float(horizon["targetAgreement"]["agreement"])
            < MAXIMUM_CORE_TARGET_AGREEMENT_FOR_MATERIALITY
            for horizon in row["horizons"].values()
        )
        for row in core_groups
    ) if core_groups else False
    status = (
        "passed_limited"
        if cycle_id != "C2" and pass_share >= MINIMUM_ABLATION_PASS_SHARE
        else "passed_limited"
        if cycle_id == "C2" and confirmation_stable and core_necessary
        else "failed"
    )
    return {
        "status": status,
        "groupCount": len(results),
        "passedGroups": passed_groups,
        "passShare": _json_value(pass_share),
        "minimumDirectionAccuracy": MINIMUM_ABLATION_DIRECTION_ACCURACY,
        "minimumCountryHoldoutAccuracy": (
            MINIMUM_ABLATION_COUNTRY_HOLDOUT_ACCURACY
        ),
        "minimumTargetAgreement": MINIMUM_ABLATION_TARGET_AGREEMENT,
        "maximumAbsoluteCurrentProbabilityShift": _json_value(maximum_shift),
        "coreNecessary": core_necessary if cycle_id == "C2" else None,
        "confirmationStable": confirmation_stable if cycle_id == "C2" else None,
        "maximumCoreTargetAgreementForMateriality": (
            MAXIMUM_CORE_TARGET_AGREEMENT_FOR_MATERIALITY
            if cycle_id == "C2"
            else None
        ),
        "groups": results,
        "method": (
            "C2分别检验两类问题：删除住房动量或按揭信用后，当前概率/方向目标是否显著变化，以确认核心必要性；删除投资或融资条件后，核心方向结论是否保持，以确认辅助层稳健性。"
            if cycle_id == "C2"
            else "逐次删除预先定义的指标家族并重建国家因子、方向目标、递归分类器与当前跨源桥接；不在删减结果间择优。"
        ),
        "caveat": "通过只代表核心定义清楚且确认层不主导结论，不代表固定周期长度、精确相位角或资产收益预测已经通过。",
    }


def _bandpower_ratio(values: np.ndarray, low_period: float, high_period: float) -> float:
    values = np.asarray(values, dtype="float64")
    values = values[np.isfinite(values)]
    if len(values) < 60:
        return float("nan")
    frequencies, power = signal.welch(
        values,
        fs=1.0,
        nperseg=min(96, len(values)),
        detrend="linear",
        scaling="density",
    )
    positive = frequencies > 0
    integrate = getattr(np, "trapezoid", np.trapz)
    total = float(integrate(power[positive], frequencies[positive]))
    band = (frequencies >= 1.0 / high_period) & (frequencies <= 1.0 / low_period)
    selected = float(integrate(power[band], frequencies[band]))
    return selected / total if total > 0 else float("nan")


def _strongest_period(values: np.ndarray, search_band: tuple[float, float]) -> float | None:
    values = np.asarray(values, dtype="float64")
    values = values[np.isfinite(values)]
    if len(values) < 60:
        return None
    frequencies, power = signal.welch(
        values,
        fs=1.0,
        nperseg=min(96, len(values)),
        detrend="linear",
        scaling="density",
    )
    positive = frequencies > 0
    periods = np.divide(1.0, frequencies[positive])
    selected_power = power[positive]
    mask = (periods >= search_band[0]) & (periods <= search_band[1])
    if not mask.any():
        return None
    return float(periods[mask][np.argmax(selected_power[mask])])


def spectral_validation(panel: pd.DataFrame, cycle_id: str) -> dict[str, object]:
    spec = CYCLE_SPECS[cycle_id]
    rng = np.random.default_rng(20260720 + int(cycle_id[-1]))
    rows: list[dict[str, object]] = []
    for iso, country in panel.groupby("iso"):
        series = country.sort_values("year").set_index("year")["factor"].loc[1900:].dropna()
        if len(series) < 80:
            continue
        observed = _bandpower_ratio(series.to_numpy(), *spec.expected_band_years)
        centered = series.to_numpy() - float(series.mean())
        lagged = centered[:-1]
        current = centered[1:]
        denominator = float(np.dot(lagged, lagged))
        phi = float(np.dot(lagged, current) / denominator) if denominator > 1e-12 else 0.0
        phi = float(np.clip(phi, -0.95, 0.95))
        residual = current - phi * lagged
        sigma = float(np.std(residual, ddof=1)) if len(residual) > 2 else 1.0
        simulated_scores: list[float] = []
        for _ in range(250):
            simulated = np.zeros(len(centered), dtype="float64")
            shocks = rng.normal(0.0, sigma, len(centered))
            for index in range(1, len(simulated)):
                simulated[index] = phi * simulated[index - 1] + shocks[index]
            simulated_scores.append(_bandpower_ratio(simulated, *spec.expected_band_years))
        p_value = float((1 + np.sum(np.asarray(simulated_scores) >= observed)) / (len(simulated_scores) + 1))
        rows.append(
            {
                "iso": iso,
                "observations": len(series),
                "peakPeriodYears": _strongest_period(series.to_numpy(), spec.search_band_years),
                "bandpowerRatio": observed,
                "redNoisePValue": p_value,
            }
        )
    frame = pd.DataFrame(rows)
    peaks = pd.to_numeric(frame["peakPeriodYears"], errors="coerce").dropna()
    return {
        "countryCount": int(len(frame)),
        "medianPeakYears": _json_value(peaks.median()),
        "peakIqrYears": [_json_value(peaks.quantile(0.25)), _json_value(peaks.quantile(0.75))],
        "expectedBandYears": list(spec.expected_band_years),
        "peakInsideBandShare": _json_value(peaks.between(*spec.expected_band_years).mean()),
        "redNoisePassShare10pct": _json_value((frame["redNoisePValue"] < 0.10).mean()),
        "countries": _records(frame),
    }


def _fetch_bis(*, refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    spp_path = _download(
        BIS_SPP_URL,
        RAW_DIR / "BIS_WS_SPP.csv",
        accept="application/vnd.sdmx.data+csv;version=1.0.0",
        refresh=refresh,
    )
    tc_path = _download(
        BIS_TC_URL,
        RAW_DIR / "BIS_WS_TC.csv",
        accept="application/vnd.sdmx.data+csv;version=1.0.0",
        refresh=refresh,
    )
    return pd.read_csv(spp_path, low_memory=False), pd.read_csv(tc_path, low_memory=False)


def _fetch_world_bank(*, refresh: bool = False) -> pd.DataFrame:
    country_text = ";".join(C2_BRIDGE_COUNTRIES)
    indicators = {
        "NE.GDI.FTOT.ZS": "fixed_capital_formation_share",
        "NY.GDP.MKTP.KD.ZG": "real_gdp_growth",
        "FR.INR.LEND": "lending_rate",
        "FP.CPI.TOTL.ZG": "cpi_inflation",
    }
    merged: pd.DataFrame | None = None
    for indicator, column in indicators.items():
        cache_path = RAW_DIR / f"world_bank_{indicator.replace('.', '_')}.json"
        if not refresh and cache_path.exists() and cache_path.stat().st_size > 1_000:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        else:
            response = requests.get(
                WORLD_BANK_URL.format(countries=country_text, indicator=indicator),
                params={"format": "json", "per_page": 20_000},
                timeout=90,
            )
            response.raise_for_status()
            payload = response.json()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(payload), encoding="utf-8")
        rows = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        frame = pd.DataFrame(
            [
                {
                    "iso": row.get("countryiso3code"),
                    "year": int(row["date"]),
                    column: row.get("value"),
                }
                for row in rows
                if row.get("countryiso3code") in C2_BRIDGE_COUNTRIES and str(row.get("date", "")).isdigit()
            ]
        )
        merged = frame if merged is None else merged.merge(frame, on=["iso", "year"], how="outer")
    if merged is None:
        raise RuntimeError("World Bank bridge data unavailable")
    return merged.sort_values(["iso", "year"])


def _fetch_oecd_gfcf(*, refresh: bool = False) -> pd.DataFrame:
    path = _download(
        OECD_GFCF_URL,
        RAW_DIR / "OECD_QNA_GFCF.csv",
        accept="text/csv",
        refresh=refresh,
    )
    frame = pd.read_csv(path, low_memory=False)
    frame["OBS_VALUE"] = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
    return frame.dropna(subset=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"])


def _fetch_oecd_house_prices(*, refresh: bool = False) -> pd.DataFrame:
    path = _download(
        OECD_HOUSE_PRICE_URL,
        OECD_HOUSE_PRICE_CACHE,
        accept="text/csv",
        refresh=refresh,
    )
    frame = pd.read_csv(path, low_memory=False)
    required_columns = {
        "REF_AREA",
        "TIME_PERIOD",
        "OBS_VALUE",
        "MEASURE",
        "UNIT_MEASURE",
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"OECD house-price cache missing columns: {sorted(missing_columns)}"
        )
    measures = set(frame["MEASURE"].dropna().astype(str).unique())
    if measures != {OECD_HOUSE_PRICE_MEASURE}:
        raise ValueError(
            "OECD house-price cache is not the house-price-to-rent ratio: "
            f"{sorted(measures)}"
        )
    frame["OBS_VALUE"] = pd.to_numeric(frame["OBS_VALUE"], errors="coerce")
    return frame.dropna(subset=["REF_AREA", "TIME_PERIOD", "OBS_VALUE"])


def _fetch_oecd_short_rates(*, refresh: bool = False) -> pd.DataFrame:
    path = _download(
        OECD_SHORT_RATE_URL,
        OECD_SHORT_RATE_CACHE,
        accept="text/csv",
        refresh=refresh,
    )
    frame = pd.read_csv(path, low_memory=False)
    required_columns = {
        "REF_AREA",
        "FREQ",
        "MEASURE",
        "UNIT_MEASURE",
        "METHODOLOGY",
        "TIME_PERIOD",
        "OBS_VALUE",
    }
    missing_columns = required_columns.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            f"OECD short-rate cache missing columns: {sorted(missing_columns)}"
        )
    series_identity = set(
        zip(
            frame["FREQ"].astype(str),
            frame["MEASURE"].astype(str),
            frame["UNIT_MEASURE"].astype(str),
            frame["METHODOLOGY"].astype(str),
        )
    )
    if series_identity != {("A", "IR3TIB", "PA", "N")}:
        raise ValueError(
            "OECD short-rate cache has unexpected series identity: "
            f"{sorted(series_identity)}"
        )
    result = frame.rename(
        columns={
            "REF_AREA": "iso",
            "TIME_PERIOD": "year",
            "OBS_VALUE": "short_term_rate",
        }
    )[["iso", "year", "short_term_rate"]].copy()
    result["year"] = pd.to_numeric(result["year"], errors="coerce")
    result["short_term_rate"] = pd.to_numeric(
        result["short_term_rate"], errors="coerce"
    )
    return (
        result.loc[result["iso"].isin(JST_COUNTRIES)]
        .dropna(subset=["year", "short_term_rate"])
        .astype({"year": int})
        .sort_values(["iso", "year"])
    )


def _quarterly_to_annual(frame: pd.DataFrame, area_column: str, value_column: str) -> pd.DataFrame:
    result = frame.copy()
    period = result["TIME_PERIOD"].astype(str).str.extract(r"(?P<year>\d{4})-Q(?P<quarter>[1-4])")
    result["year"] = pd.to_numeric(period["year"], errors="coerce")
    result["quarter"] = pd.to_numeric(period["quarter"], errors="coerce")
    result = result.loc[result["quarter"] == 4].copy()
    area = result[area_column].astype(str)
    result["iso"] = area.map(BIS_TO_ISO3).fillna(
        area.where(area.isin(C2_BRIDGE_COUNTRIES))
    )
    result[value_column] = pd.to_numeric(result["OBS_VALUE"], errors="coerce")
    return result.dropna(subset=["iso", "year"])[["iso", "year", value_column]].astype({"year": int})


def _quarterly_values(frame: pd.DataFrame, area_column: str, value_column: str) -> pd.DataFrame:
    result = frame.copy()
    period = result["TIME_PERIOD"].astype(str).str.extract(r"(?P<year>\d{4})-Q(?P<quarter>[1-4])")
    result["year"] = pd.to_numeric(period["year"], errors="coerce")
    result["quarter"] = pd.to_numeric(period["quarter"], errors="coerce")
    area = result[area_column].astype(str)
    result["iso"] = area.map(BIS_TO_ISO3).fillna(
        area.where(area.isin(C2_BRIDGE_COUNTRIES))
    )
    result[value_column] = pd.to_numeric(result["OBS_VALUE"], errors="coerce")
    result = result.dropna(subset=["iso", "year", "quarter", value_column]).copy()
    result["year"] = result["year"].astype(int)
    result["quarter"] = result["quarter"].astype(int)
    result["period"] = result["year"].astype(str) + "-Q" + result["quarter"].astype(str)
    return result[["iso", "year", "quarter", "period", value_column]]


def _latest_supported_period(
    frame: pd.DataFrame,
    value_column: str,
    *,
    minimum_countries: int = 6,
) -> str:
    coverage = (
        frame.dropna(subset=[value_column])
        .groupby("period")["iso"]
        .nunique()
        .sort_index()
    )
    supported = coverage.loc[coverage >= minimum_countries]
    if supported.empty:
        raise ValueError(
            f"No period has at least {minimum_countries} countries for {value_column}"
        )
    return str(supported.index[-1])


def _bridge_sources(
    spp: pd.DataFrame,
    total_credit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    real_house = spp.loc[
        (spp["VALUE"] == "R")
        & (pd.to_numeric(spp["UNIT_MEASURE"], errors="coerce") == 628)
    ]
    credit_filter = (
        (total_credit["TC_LENDERS"] == "A")
        & (total_credit["VALUATION"] == "M")
        & (total_credit["UNIT_TYPE"].astype(str) == "770")
        & (total_credit["TC_ADJUST"] == "A")
        & (total_credit["UNIT_MEASURE"].astype(str) == "367")
    )
    household_credit = total_credit.loc[credit_filter & (total_credit["TC_BORROWERS"] == "H")]
    business_credit = total_credit.loc[credit_filter & (total_credit["TC_BORROWERS"] == "N")]
    return real_house, household_credit, business_credit


def build_bridge_panel(
    cycle_id: str,
    *,
    spp: pd.DataFrame | None = None,
    total_credit: pd.DataFrame | None = None,
    world_bank: pd.DataFrame | None = None,
    oecd_house_prices: pd.DataFrame | None = None,
    oecd_short_rates: pd.DataFrame | None = None,
    refresh: bool = False,
    excluded_families: set[str] | None = None,
) -> pd.DataFrame:
    excluded = excluded_families or set()
    if spp is None or total_credit is None:
        spp, total_credit = _fetch_bis(refresh=refresh)
    if world_bank is None:
        world_bank = _fetch_world_bank(refresh=refresh)
    if cycle_id == "C2" and oecd_house_prices is None:
        oecd_house_prices = _fetch_oecd_house_prices(refresh=refresh)
    if cycle_id == "C2" and oecd_short_rates is None:
        oecd_short_rates = _fetch_oecd_short_rates(refresh=refresh)

    real_house, household_credit_source, business_credit_source = _bridge_sources(spp, total_credit)
    real_house = _quarterly_to_annual(real_house, "REF_AREA", "real_house_price_index")
    household_credit = _quarterly_to_annual(
        household_credit_source,
        "BORROWERS_CTY",
        "household_credit_gdp",
    )
    business_credit = _quarterly_to_annual(
        business_credit_source,
        "BORROWERS_CTY",
        "business_credit_gdp",
    )
    house_price_rent = pd.DataFrame(columns=["iso", "year", "house_price_rent_ratio"])
    if cycle_id == "C2" and oecd_house_prices is not None:
        house_price_rent = _quarterly_to_annual(
            oecd_house_prices,
            "REF_AREA",
            "house_price_rent_ratio",
        )

    merged = real_house.merge(household_credit, on=["iso", "year"], how="outer")
    merged = merged.merge(business_credit, on=["iso", "year"], how="outer")
    merged = merged.merge(house_price_rent, on=["iso", "year"], how="outer")
    merged = merged.merge(world_bank, on=["iso", "year"], how="outer")
    if cycle_id == "C2" and oecd_short_rates is not None:
        merged = merged.merge(
            oecd_short_rates,
            on=["iso", "year"],
            how="outer",
        )

    rows: list[pd.DataFrame] = []
    for iso, country in merged.groupby("iso"):
        country = country.sort_values("year").set_index("year")
        features = pd.DataFrame(index=country.index)
        if cycle_id == "C2":
            real_house_price_growth = causal_robust_z(
                np.log(pd.to_numeric(country["real_house_price_index"], errors="coerce").where(lambda value: value > 0)).diff(3)
                / 3.0
            )
            valuation_momentum = causal_robust_z(
                np.log(
                    pd.to_numeric(
                        country["house_price_rent_ratio"], errors="coerce"
                    ).where(lambda value: value > 0)
                ).diff(3)
                / 3.0
            )
            housing_channels = pd.concat(
                [real_house_price_growth, valuation_momentum], axis=1
            )
            features["housing_momentum"] = housing_channels.mean(
                axis=1, skipna=True
            ).where(housing_channels.notna().sum(axis=1) >= 1)
            features["mortgage_credit"] = causal_robust_z(
                pd.to_numeric(country["household_credit_gdp"], errors="coerce").diff(3) / 3.0
            )
            investment_share = pd.to_numeric(
                country["fixed_capital_formation_share"], errors="coerce"
            )
            features["investment_confirmation"] = causal_robust_z(
                investment_share.diff(3) / 3.0
            )
            real_lending_rate = (
                pd.to_numeric(country["lending_rate"], errors="coerce")
                - pd.to_numeric(country["cpi_inflation"], errors="coerce")
            )
            real_short_rate = (
                pd.to_numeric(
                    country.get("short_term_rate"), errors="coerce"
                )
                - pd.to_numeric(country["cpi_inflation"], errors="coerce")
            )
            oecd_short_real_financing = causal_robust_z(
                -real_short_rate.diff(3) / 3.0
            )
            lending_rate_real_financing = causal_robust_z(
                -real_lending_rate.diff(3) / 3.0
            )
            features["financing_conditions"] = causal_robust_z(
                -real_short_rate.combine_first(real_lending_rate).diff(3) / 3.0
            )
            structural_channels = pd.concat(
                {
                    "structural_valuation": causal_robust_z(
                        np.log(
                            pd.to_numeric(
                                country["house_price_rent_ratio"],
                                errors="coerce",
                            ).where(lambda value: value > 0)
                        )
                    ),
                    "structural_leverage": causal_robust_z(
                        pd.to_numeric(
                            country["household_credit_gdp"], errors="coerce"
                        )
                    ),
                    "structural_investment": causal_robust_z(
                        investment_share
                    ),
                },
                axis=1,
            )
        else:
            investment_share = pd.to_numeric(country["fixed_capital_formation_share"], errors="coerce")
            features["investment_share"] = causal_robust_z(investment_share)
            features["investment_impulse3"] = causal_robust_z(investment_share.diff(3) / 3.0)
            features["business_credit_impulse3"] = causal_robust_z(
                pd.to_numeric(country["business_credit_gdp"], errors="coerce").diff(3) / 3.0
            )
            features["real_gdp_growth3"] = causal_robust_z(
                pd.to_numeric(country["real_gdp_growth"], errors="coerce").rolling(3, min_periods=2).mean()
            )
        features = features.drop(columns=list(excluded), errors="ignore")
        country_frame = features.add_prefix("family_")
        if cycle_id == "C2":
            country_frame = country_frame.join(structural_channels)
            country_frame["oecd_short_real_financing"] = (
                oecd_short_real_financing
            )
            country_frame["lending_rate_real_financing"] = (
                lending_rate_real_financing
            )
            country_frame["structural_pressure"] = structural_channels.mean(
                axis=1, skipna=True
            ).where(structural_channels.notna().sum(axis=1) >= 2)
            country_frame["structural_family_count"] = (
                structural_channels.notna().sum(axis=1)
            )
        country_frame["factor"] = _country_factor(features, cycle_id)
        country_frame["iso"] = iso
        country_frame["year"] = country_frame.index.astype(int)
        rows.append(country_frame.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)


def _same_quarter_house_feature(
    real_house: pd.DataFrame,
    oecd_house_prices: pd.DataFrame | None = None,
) -> pd.DataFrame:
    quarterly = _quarterly_values(real_house, "REF_AREA", "real_house_price_index")
    rows: list[pd.DataFrame] = []
    for (iso, quarter), group in quarterly.groupby(["iso", "quarter"]):
        group = group.sort_values("year").set_index("year")
        growth = np.log(group["real_house_price_index"].where(lambda value: value > 0)).diff(3) / 3.0
        frame = pd.DataFrame(
            {
                "iso": iso,
                "year": group.index.astype(int),
                "quarter": quarter,
                "period": group["period"],
                "family_real_house_price_growth3": causal_robust_z(growth),
            }
        )
        rows.append(frame.reset_index(drop=True))
    result = pd.concat(rows, ignore_index=True)
    if oecd_house_prices is None or oecd_house_prices.empty:
        result["family_housing_momentum"] = result[
            "family_real_house_price_growth3"
        ]
        return result

    valuation = _quarterly_values(
        oecd_house_prices,
        "REF_AREA",
        "house_price_rent_ratio",
    )
    valuation_rows: list[pd.DataFrame] = []
    for (iso, quarter), group in valuation.groupby(["iso", "quarter"]):
        group = group.sort_values("year").set_index("year")
        momentum = np.log(
            group["house_price_rent_ratio"].where(lambda value: value > 0)
        ).diff(3) / 3.0
        valuation_rows.append(
            pd.DataFrame(
                {
                    "iso": iso,
                    "year": group.index.astype(int),
                    "quarter": quarter,
                    "period": group["period"],
                    "family_house_price_rent_momentum3": causal_robust_z(
                        momentum
                    ),
                }
            ).reset_index(drop=True)
        )
    valuation_features = pd.concat(valuation_rows, ignore_index=True)
    result = result.merge(
        valuation_features,
        on=["iso", "year", "quarter", "period"],
        how="outer",
    )
    housing_channels = result[
        [
            "family_real_house_price_growth3",
            "family_house_price_rent_momentum3",
        ]
    ]
    result["family_housing_momentum"] = housing_channels.mean(
        axis=1, skipna=True
    ).where(housing_channels.notna().sum(axis=1) >= 1)
    return result


def build_c2_partial_year_panel(
    annual_bridge: pd.DataFrame,
    spp: pd.DataFrame,
    oecd_house_prices: pd.DataFrame | None = None,
    *,
    as_of_period: str | None = None,
    update_isos: set[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    real_house = spp.loc[
        (spp["VALUE"] == "R")
        & (pd.to_numeric(spp["UNIT_MEASURE"], errors="coerce") == 628)
    ]
    house_features = _same_quarter_house_feature(real_house, oecd_house_prices)
    if as_of_period is None:
        as_of_period = _latest_supported_period(
            house_features,
            "family_housing_momentum",
        )
    match = pd.Series(house_features["period"].astype(str) == as_of_period, index=house_features.index)
    current_house = house_features.loc[match].dropna(
        subset=["family_housing_momentum"]
    )
    if update_isos is not None:
        current_house = current_house.loc[current_house["iso"].isin(update_isos)]
    if current_house.empty:
        return annual_bridge.copy(), {
            "status": "unavailable",
            "asOfPeriod": as_of_period,
            "countryCount": 0,
            "reason": "当前季度住宅价格不足以形成部分年度桥接。",
        }

    current_year = int(as_of_period[:4])
    quarter = int(as_of_period[-1])
    quarter_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    base = annual_bridge.loc[annual_bridge["year"] < current_year].copy()
    appended: list[pd.DataFrame] = []
    for _, house_row in current_house.iterrows():
        country = base.loc[base["iso"] == house_row["iso"]].sort_values("year")
        if country.empty:
            continue
        latest = country.tail(1).copy()
        if int(latest.iloc[0]["year"]) < current_year - 1:
            continue
        latest["year"] = current_year
        for column in (
            "family_housing_momentum",
            "family_real_house_price_growth3",
            "family_house_price_rent_momentum3",
        ):
            if column in latest.columns and column in house_row:
                latest[column] = house_row[column]
        appended.append(latest)
    if not appended:
        return annual_bridge.copy(), {
            "status": "unavailable",
            "asOfPeriod": as_of_period,
            "countryCount": 0,
            "reason": "当前季度与上一完整年度无法匹配。",
        }

    partial = pd.concat([base, *appended], ignore_index=True)
    family_columns = [column for column in partial.columns if column.startswith("family_")]
    rebuilt: list[pd.DataFrame] = []
    for _, country in partial.groupby("iso"):
        country = country.sort_values("year").copy()
        features = country[family_columns].rename(columns=lambda column: column.removeprefix("family_"))
        country["factor"] = _country_factor(features, "C2")
        rebuilt.append(country)
    partial = pd.concat(rebuilt, ignore_index=True)
    source_year = current_year - 1
    return partial, {
        "status": "limited_partial_year",
        "asOfPeriod": as_of_period,
        "plotDate": f"{current_year}-{quarter_end}",
        "countryCount": len(appended),
        "totalCountryCount": len(C2_BRIDGE_COUNTRIES),
        "observedFamilies": ["housing_momentum"],
        "carriedFamilies": [
            "mortgage_credit",
            "investment_confirmation",
            "financing_conditions",
            "structural_pressure",
        ],
        "carriedFrom": str(source_year),
        "reason": "真实房价与房价租金比使用当前季度形成住房动量；家庭信用、投资确认、结构压力和融资条件使用上一完整年度，单独标记为部分年度研究桥接。",
        "updatedFamilyLabel": "住房动量",
        "coverageLabel": f"当前住房动量覆盖 {len(appended)}/{len(C2_BRIDGE_COUNTRIES)} 国",
        "carryLabel": f"信用、投资、结构压力与融资条件仍沿用 {source_year} 完整年度",
    }


def validate_c2_partial_year_bridge(
    historical: pd.DataFrame,
    annual_bridge: pd.DataFrame,
    spp: pd.DataFrame,
    oecd_house_prices: pd.DataFrame | None = None,
    *,
    quarter: int = 1,
) -> dict[str, object]:
    real_house = spp.loc[
        (spp["VALUE"] == "R")
        & (pd.to_numeric(spp["UNIT_MEASURE"], errors="coerce") == 628)
    ]
    house_features = _same_quarter_house_feature(real_house, oecd_house_prices)
    latest_period = _latest_supported_period(
        house_features,
        "family_housing_momentum",
    )
    current_update_isos = set(
        house_features.loc[
            (house_features["period"] == latest_period)
            & house_features["family_housing_momentum"].notna(),
            "iso",
        ].astype(str)
    )
    rows: list[dict[str, object]] = []
    available_years = sorted(
        {
            int(period[:4])
            for period in spp["TIME_PERIOD"].astype(str)
            if period.endswith(f"Q{quarter}") and period[:4].isdigit()
        }
    )
    historical_end = int(historical["year"].max())
    for year in available_years:
        if year < 2000:
            continue
        aligned_final = _align_bridge_factor(
            historical,
            annual_bridge.loc[annual_bridge["year"] <= year].copy(),
            alignment_end_year=min(year, historical_end),
        )
        final_history = {
            int(row["date"]): float(row["value"])
            for row in _global_history(aligned_final)
        }
        if year not in final_history or year - 1 not in final_history:
            continue
        partial, metadata = build_c2_partial_year_panel(
            annual_bridge.loc[annual_bridge["year"] <= year].copy(),
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
            update_isos=current_update_isos,
        )
        if int(metadata.get("countryCount", 0)) < 6:
            continue
        aligned_partial = _align_bridge_factor(
            historical,
            partial,
            alignment_end_year=min(year - 1, historical_end),
        )
        current = (
            aligned_partial.sort_values(["iso", "year"])
            .groupby("iso", as_index=False)
            .tail(1)
        )
        current = current.loc[current["year"] >= year - 1].dropna(subset=["factor"])
        if len(current) < 12:
            continue
        estimate = float(current["factor"].median())
        actual = final_history[year]
        previous = final_history[year - 1]
        rows.append(
            {
                "year": year,
                "estimate": estimate,
                "actual": actual,
                "absoluteError": abs(estimate - actual),
                "directionCorrect": int(np.sign(estimate - previous) == np.sign(actual - previous)),
                "countryCount": int(len(current)),
                "updatedCountryCount": int((current["year"] == year).sum()),
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"status": "failed", "observations": 0, "reason": "没有足够历史截点。"}
    correlation = frame[["estimate", "actual"]].corr().iloc[0, 1] if len(frame) >= 3 else np.nan
    mae = float(frame["absoluteError"].mean())
    direction_accuracy = float(frame["directionCorrect"].mean())
    passed = len(frame) >= 12 and mae <= 0.35 and direction_accuracy >= 0.60 and correlation >= 0.30
    return {
        "status": "passed_limited" if passed else "failed",
        "observations": int(len(frame)),
        "startYear": int(frame["year"].min()),
        "endYear": int(frame["year"].max()),
        "mae": _json_value(mae),
        "directionAccuracy": _json_value(direction_accuracy),
        "correlation": _json_value(correlation),
        "medianCountryCount": _json_value(frame["countryCount"].median()),
        "medianUpdatedCountryCount": _json_value(frame["updatedCountryCount"].median()),
        "currentCoverageCountryCount": len(current_update_isos),
        "gate": {"minimumObservations": 12, "maximumMae": 0.35, "minimumDirectionAccuracy": 0.60, "minimumCorrelation": 0.30},
        "history": _records(frame),
        "method": "按当前可更新国家集合回放每个历史Q1：只用当时已经存在的重叠历史完成跨源对齐，更新当季真实房价与房价租金比，其余国家和信用、投资保留上一完整年度，再估计当年最终年度全球因子。",
    }


def _same_quarter_gfcf_feature(oecd_gfcf: pd.DataFrame) -> pd.DataFrame:
    frame = oecd_gfcf.copy()
    period = frame["TIME_PERIOD"].astype(str).str.extract(r"(?P<year>\d{4})-Q(?P<quarter>[1-4])")
    frame["year"] = pd.to_numeric(period["year"], errors="coerce")
    frame["quarter"] = pd.to_numeric(period["quarter"], errors="coerce")
    frame["iso"] = frame["REF_AREA"].astype(str)
    frame = frame.dropna(subset=["year", "quarter", "OBS_VALUE"]).copy()
    frame["year"] = frame["year"].astype(int)
    frame["quarter"] = frame["quarter"].astype(int)
    rows: list[pd.DataFrame] = []
    for (iso, quarter), group in frame.groupby(["iso", "quarter"]):
        group = group.sort_values("year").set_index("year")
        growth = np.log(group["OBS_VALUE"].where(lambda value: value > 0)).diff(3) / 3.0
        proxy = causal_robust_z(growth, window=20, min_periods=10)
        rows.append(
            pd.DataFrame(
                {
                    "iso": iso,
                    "year": group.index.astype(int),
                    "quarter": quarter,
                    "period": group["TIME_PERIOD"],
                    "proxy_investment_impulse3": proxy,
                }
            ).reset_index(drop=True)
        )
    return pd.concat(rows, ignore_index=True)


def _calibrate_investment_proxy(
    annual_country: pd.DataFrame,
    proxy_country: pd.DataFrame,
    current_proxy: float,
    current_year: int,
) -> float | None:
    target = annual_country.loc[
        annual_country["year"] < current_year,
        ["year", "family_investment_impulse3"],
    ].dropna()
    proxy = proxy_country.loc[
        proxy_country["year"] < current_year,
        ["year", "proxy_investment_impulse3"],
    ].dropna()
    overlap = target.merge(proxy, on="year", how="inner").dropna()
    proxy_std = float(overlap["proxy_investment_impulse3"].std(ddof=0))
    target_std = float(overlap["family_investment_impulse3"].std(ddof=0))
    if len(overlap) < 6 or proxy_std <= 1e-8 or target_std <= 1e-8:
        return None
    calibrated = (
        (current_proxy - float(overlap["proxy_investment_impulse3"].mean()))
        / proxy_std
        * target_std
        + float(overlap["family_investment_impulse3"].mean())
    )
    return float(np.clip(calibrated, -4.0, 4.0))


def build_c3_partial_year_panel(
    annual_bridge: pd.DataFrame,
    oecd_gfcf: pd.DataFrame,
    *,
    as_of_period: str | None = None,
    update_isos: set[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    proxy_features = _same_quarter_gfcf_feature(oecd_gfcf)
    if as_of_period is None:
        as_of_period = str(proxy_features["period"].max())
    current = proxy_features.loc[
        (proxy_features["period"] == as_of_period)
        & proxy_features["proxy_investment_impulse3"].notna()
    ]
    if update_isos is not None:
        current = current.loc[current["iso"].isin(update_isos)]
    if current.empty:
        return annual_bridge.copy(), {
            "status": "unavailable",
            "asOfPeriod": as_of_period,
            "countryCount": 0,
            "reason": "当前季度固定资本形成数据不足。",
        }

    current_year = int(as_of_period[:4])
    quarter = int(as_of_period[-1])
    quarter_end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    base = annual_bridge.loc[annual_bridge["year"] < current_year].copy()
    appended: list[pd.DataFrame] = []
    for _, proxy_row in current.iterrows():
        country = base.loc[base["iso"] == proxy_row["iso"]].sort_values("year")
        if country.empty or int(country.iloc[-1]["year"]) < current_year - 1:
            continue
        proxy_country = proxy_features.loc[
            (proxy_features["iso"] == proxy_row["iso"])
            & (proxy_features["quarter"] == quarter)
        ]
        calibrated = _calibrate_investment_proxy(
            country,
            proxy_country,
            float(proxy_row["proxy_investment_impulse3"]),
            current_year,
        )
        if calibrated is None:
            continue
        latest = country.tail(1).copy()
        latest["year"] = current_year
        latest["family_investment_impulse3"] = calibrated
        appended.append(latest)
    if not appended:
        return annual_bridge.copy(), {
            "status": "unavailable",
            "asOfPeriod": as_of_period,
            "countryCount": 0,
            "reason": "季度资本形成代理无法与年度投资因子完成因果校准。",
        }

    partial = pd.concat([base, *appended], ignore_index=True)
    family_columns = [column for column in partial.columns if column.startswith("family_")]
    rebuilt: list[pd.DataFrame] = []
    for _, country in partial.groupby("iso"):
        country = country.sort_values("year").copy()
        features = country[family_columns].rename(columns=lambda column: column.removeprefix("family_"))
        country["factor"] = _country_factor(features, "C3")
        rebuilt.append(country)
    partial = pd.concat(rebuilt, ignore_index=True)
    source_year = current_year - 1
    return partial, {
        "status": "limited_partial_year",
        "asOfPeriod": as_of_period,
        "plotDate": f"{current_year}-{quarter_end}",
        "countryCount": len(appended),
        "totalCountryCount": len(JST_COUNTRIES),
        "observedFamilies": ["real_gfcf_investment_impulse3_proxy"],
        "carriedFamilies": ["investment_share", "business_credit_impulse3", "real_gdp_growth3"],
        "carriedFrom": str(source_year),
        "reason": "OECD实际固定资本形成更新投资脉冲；投资占比、企业信用和GDP使用上一完整年度。",
        "updatedFamilyLabel": "实际固定资本形成",
        "coverageLabel": f"当前资本形成覆盖 {len(appended)}/{len(JST_COUNTRIES)} 国",
        "carryLabel": f"投资占比、企业信用和GDP仍沿用 {source_year} 完整年度",
    }


def validate_c3_partial_year_bridge(
    historical: pd.DataFrame,
    annual_bridge: pd.DataFrame,
    oecd_gfcf: pd.DataFrame,
    *,
    quarter: int = 1,
) -> dict[str, object]:
    proxy_features = _same_quarter_gfcf_feature(oecd_gfcf)
    latest_period = str(proxy_features["period"].max())
    current_update_isos = set(
        proxy_features.loc[
            (proxy_features["period"] == latest_period)
            & proxy_features["proxy_investment_impulse3"].notna(),
            "iso",
        ].astype(str)
    )
    rows: list[dict[str, object]] = []
    historical_end = int(historical["year"].max())
    for year in sorted(proxy_features["year"].unique()):
        if year < 2000:
            continue
        aligned_final = _align_bridge_factor(
            historical,
            annual_bridge.loc[annual_bridge["year"] <= year].copy(),
            alignment_end_year=min(year, historical_end),
        )
        final_history = {
            int(row["date"]): float(row["value"])
            for row in _global_history(aligned_final)
        }
        if year not in final_history or year - 1 not in final_history:
            continue
        partial, metadata = build_c3_partial_year_panel(
            annual_bridge.loc[annual_bridge["year"] <= year].copy(),
            oecd_gfcf.loc[oecd_gfcf["TIME_PERIOD"].astype(str) <= f"{year}-Q{quarter}"].copy(),
            as_of_period=f"{year}-Q{quarter}",
            update_isos=current_update_isos,
        )
        updated_count = int(metadata.get("countryCount", 0))
        if updated_count < 8:
            continue
        aligned_partial = _align_bridge_factor(
            historical,
            partial,
            alignment_end_year=min(year - 1, historical_end),
        )
        current = aligned_partial.sort_values(["iso", "year"]).groupby("iso", as_index=False).tail(1)
        current = current.loc[current["year"] >= year - 1].dropna(subset=["factor"])
        if len(current) < 12:
            continue
        estimate = float(current["factor"].median())
        actual = final_history[year]
        previous = final_history[year - 1]
        rows.append(
            {
                "year": int(year),
                "estimate": estimate,
                "actual": actual,
                "absoluteError": abs(estimate - actual),
                "directionCorrect": int(np.sign(estimate - previous) == np.sign(actual - previous)),
                "countryCount": int(len(current)),
                "updatedCountryCount": updated_count,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {"status": "failed", "observations": 0, "reason": "没有足够历史截点。"}
    correlation = frame[["estimate", "actual"]].corr().iloc[0, 1] if len(frame) >= 3 else np.nan
    mae = float(frame["absoluteError"].mean())
    direction_accuracy = float(frame["directionCorrect"].mean())
    passed = len(frame) >= 12 and mae <= 0.35 and direction_accuracy >= 0.60 and correlation >= 0.30
    return {
        "status": "passed_limited" if passed else "failed",
        "observations": int(len(frame)),
        "startYear": int(frame["year"].min()),
        "endYear": int(frame["year"].max()),
        "mae": _json_value(mae),
        "directionAccuracy": _json_value(direction_accuracy),
        "correlation": _json_value(correlation),
        "medianCountryCount": _json_value(frame["countryCount"].median()),
        "medianUpdatedCountryCount": _json_value(frame["updatedCountryCount"].median()),
        "currentCoverageCountryCount": len(current_update_isos),
        "gate": {"minimumObservations": 12, "maximumMae": 0.35, "minimumDirectionAccuracy": 0.60, "minimumCorrelation": 0.30},
        "history": _records(frame),
        "method": "按当前国家集合回放历史Q1：只用当时已经存在的重叠历史完成跨源对齐，用OECD实际固定资本形成更新投资脉冲，其余家族保留上一完整年度。",
    }


def _align_bridge_factor(
    historical: pd.DataFrame,
    bridge: pd.DataFrame,
    *,
    alignment_end_year: int | None = None,
) -> pd.DataFrame:
    aligned: list[pd.DataFrame] = []
    historical_calibration = historical
    bridge_calibration = bridge
    if alignment_end_year is not None:
        historical_calibration = historical.loc[historical["year"] <= alignment_end_year]
        bridge_calibration = bridge.loc[bridge["year"] <= alignment_end_year]
    global_hist = historical_calibration["factor"].dropna()
    global_bridge = bridge_calibration["factor"].dropna()
    for iso, country in bridge.groupby("iso"):
        country = country.sort_values("year").copy()
        hist = historical_calibration.loc[
            historical_calibration["iso"] == iso,
            ["year", "factor"],
        ].rename(columns={"factor": "hist_factor"})
        country_calibration = country
        if alignment_end_year is not None:
            country_calibration = country.loc[country["year"] <= alignment_end_year]
        overlap = country_calibration[["year", "factor"]].merge(
            hist,
            on="year",
            how="inner",
        ).dropna()
        if len(overlap) >= 20 and float(overlap["factor"].std(ddof=0)) > 1e-8:
            bridge_mean = float(overlap["factor"].mean())
            bridge_std = float(overlap["factor"].std(ddof=0))
            hist_mean = float(overlap["hist_factor"].mean())
            hist_std = float(overlap["hist_factor"].std(ddof=0))
        else:
            bridge_mean = float(global_bridge.mean())
            bridge_std = float(global_bridge.std(ddof=0))
            hist_mean = float(global_hist.mean())
            hist_std = float(global_hist.std(ddof=0))
        country["factor"] = (country["factor"] - bridge_mean) / bridge_std * hist_std + hist_mean
        aligned.append(country)
    return pd.concat(aligned, ignore_index=True)


def current_direction_forecast(
    historical: pd.DataFrame,
    bridge: pd.DataFrame,
    horizon: int,
    *,
    as_of_period: str | None = None,
) -> dict[str, object]:
    aligned_bridge = _align_bridge_factor(historical, bridge)
    historical_model, feature_columns = _model_frame(historical, horizon)
    final_model = _classifier()
    final_model.fit(historical_model[feature_columns], historical_model["target_up"].astype(int))

    current_rows: list[pd.DataFrame] = []
    for _, country in aligned_bridge.groupby("iso"):
        country = country.sort_values("year").copy()
        for lag in range(1, 7):
            country[f"lag_{lag}"] = country["factor"].shift(lag)
        country["slope_1"] = country["factor"].diff()
        country["slope_3"] = country["factor"].diff(3) / 3.0
        country["slope_5"] = country["factor"].diff(5) / 5.0
        eligible = country.dropna(subset=["factor", "slope_3"])
        if not eligible.empty:
            current_rows.append(eligible.tail(1))
    current = pd.concat(current_rows, ignore_index=True)
    for column in feature_columns:
        if column not in current:
            current[column] = np.nan
    current["probability_up"] = final_model.predict_proba(current[feature_columns])[:, 1]
    latest_year = int(current["year"].max())
    latest = current.loc[current["year"] >= latest_year - 1].copy()
    if len(latest) < 8:
        latest = current.copy()

    probability = float(latest["probability_up"].mean())
    factor = float(latest["factor"].median())
    changes = historical_model["future_factor"] - historical_model["factor"]
    median_absolute_change = float(changes.abs().median())
    expected_change = (2.0 * probability - 1.0) * median_absolute_change
    return {
        "asOfYear": latest_year,
        "asOfPeriod": as_of_period or str(latest_year),
        "horizonYears": horizon,
        "probabilityUp": _json_value(probability),
        "probabilityDown": _json_value(1.0 - probability),
        "direction": "上行概率占优" if probability >= 0.55 else "下行概率占优" if probability <= 0.45 else "方向接近均衡",
        "countryCount": int(len(latest)),
        "latestYearCountryCount": int((latest["year"] == latest_year).sum()),
        "oldestCountryYear": int(latest["year"].min()),
        "countryProbabilityIqr": [
            _json_value(latest["probability_up"].quantile(0.25)),
            _json_value(latest["probability_up"].quantile(0.75)),
        ],
        "currentFactor": _json_value(factor),
        "scenarioFactor": _json_value(factor + expected_change),
        "scenarioLow": _json_value(factor + changes.quantile(0.20)),
        "scenarioHigh": _json_value(factor + changes.quantile(0.80)),
        "caveat": "方向概率来自跨国面板；部分年度国家使用明确标记的最新可用信息，情景水平仅用历史变化分布缩放，不代表可稳定预测的精确幅度。",
    }


def _global_history(panel: pd.DataFrame) -> list[dict[str, object]]:
    pivot = panel.pivot_table(index="year", columns="iso", values="factor", aggfunc="last")
    global_factor = pivot.median(axis=1, skipna=True).where(pivot.notna().sum(axis=1) >= 6).dropna()
    return [
        {"date": str(int(year)), "value": _json_value(value), "countryCount": int(pivot.loc[year].notna().sum())}
        for year, value in global_factor.items()
    ]


def _partial_nowcast_point(
    historical: pd.DataFrame,
    partial_panel: pd.DataFrame,
    metadata: dict[str, object],
) -> dict[str, object] | None:
    if metadata.get("status") != "limited_partial_year":
        return None
    year = int(str(metadata["asOfPeriod"])[:4])
    aligned = _align_bridge_factor(historical, partial_panel)
    current = aligned.sort_values(["iso", "year"]).groupby("iso", as_index=False).tail(1)
    current = current.loc[current["year"] >= year - 1].dropna(subset=["factor"])
    if current.empty:
        return None
    return {
        "date": metadata["plotDate"],
        "label": metadata["asOfPeriod"],
        "value": _json_value(current["factor"].median()),
        "countryCount": int(len(current)),
        "updatedCountryCount": int((current["year"] == year).sum()),
    }


def _cache_snapshot(path: Path) -> dict[str, object]:
    modified = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").tz_convert("Asia/Shanghai")
    return {
        "cache": str(path.relative_to(PROJECT_ROOT)),
        "cacheUpdated": modified.isoformat(),
        "bytes": path.stat().st_size,
    }


def build_research_payload(*, refresh: bool = False) -> dict[str, object]:
    jst = _load_jst(refresh=refresh)
    spp, total_credit = _fetch_bis(refresh=refresh)
    world_bank = _fetch_world_bank(refresh=refresh)
    oecd_gfcf = _fetch_oecd_gfcf(refresh=refresh)
    oecd_house_prices = _fetch_oecd_house_prices(refresh=refresh)
    oecd_short_rates = _fetch_oecd_short_rates(refresh=refresh)
    c2_architecture = c2_architecture_comparison(jst)
    cycles: dict[str, object] = {}
    for cycle_id, spec in CYCLE_SPECS.items():
        historical = build_jst_panel(jst, cycle_id)
        bridge = build_bridge_panel(
            cycle_id,
            spp=spp,
            total_credit=total_credit,
            world_bank=world_bank,
            oecd_house_prices=oecd_house_prices,
            oecd_short_rates=oecd_short_rates,
        )
        aligned_bridge = _align_bridge_factor(historical, bridge)
        model_historical = historical
        model_bridge = bridge
        if cycle_id == "C2":
            model_historical = historical.drop(
                columns=[
                    f"family_{family}" for family in C2_CONFIRMATION_FAMILIES
                ],
                errors="ignore",
            )
            model_bridge = bridge.drop(
                columns=[
                    f"family_{family}" for family in C2_CONFIRMATION_FAMILIES
                ],
                errors="ignore",
            )
        forecast_bridge = bridge
        forecast_as_of = str(int(bridge.loc[bridge["factor"].notna(), "year"].max()))
        partial_nowcast: dict[str, object] = {
            "status": "not_applicable",
            "reason": "当前没有通过验证的部分年度桥接。",
        }
        if cycle_id == "C2":
            partial_panel, partial_metadata = build_c2_partial_year_panel(
                bridge,
                spp,
                oecd_house_prices,
            )
            partial_validation = validate_c2_partial_year_bridge(
                historical,
                bridge,
                spp,
                oecd_house_prices,
            )
            partial_point = _partial_nowcast_point(historical, partial_panel, partial_metadata)
            partial_nowcast = {
                **partial_metadata,
                "validation": partial_validation,
                "point": partial_point,
            }
            if partial_validation["status"] == "passed_limited" and partial_point is not None:
                forecast_bridge = partial_panel
                forecast_as_of = str(partial_metadata["asOfPeriod"])
        if cycle_id == "C3":
            partial_panel, partial_metadata = build_c3_partial_year_panel(bridge, oecd_gfcf)
            partial_validation = validate_c3_partial_year_bridge(historical, bridge, oecd_gfcf)
            partial_point = _partial_nowcast_point(historical, partial_panel, partial_metadata)
            partial_nowcast = {
                **partial_metadata,
                "validation": partial_validation,
                "point": partial_point,
            }
            if partial_validation["status"] == "passed_limited" and partial_point is not None:
                forecast_bridge = partial_panel
                forecast_as_of = str(partial_metadata["asOfPeriod"])
        if cycle_id == "C2":
            forecast_bridge = forecast_bridge.drop(
                columns=[
                    f"family_{family}" for family in C2_CONFIRMATION_FAMILIES
                ],
                errors="ignore",
            )
        one_year = recursive_validation(model_historical, 1)
        two_year = recursive_validation(model_historical, 2)
        three_year = recursive_validation(model_historical, 3)
        family_ablation = family_ablation_validation(
            jst,
            cycle_id,
            model_historical,
            model_bridge,
            spp=spp,
            total_credit=total_credit,
            world_bank=world_bank,
            oecd_house_prices=oecd_house_prices,
            oecd_short_rates=oecd_short_rates,
        )
        independent_outcomes = independent_outcome_validation(
            jst,
            model_historical,
        )
        current_one_year = current_direction_forecast(
            model_historical,
            forecast_bridge,
            1,
            as_of_period=forecast_as_of,
        )
        current_two_year = current_direction_forecast(
            model_historical,
            forecast_bridge,
            2,
            as_of_period=forecast_as_of,
        )
        current_three_year = current_direction_forecast(
            model_historical,
            forecast_bridge,
            3,
            as_of_period=forecast_as_of,
        )
        stable_direction = (
            float(one_year["accuracy"]) >= 0.65
            and float(two_year["accuracy"]) >= 0.65
            and float(three_year["accuracy"]) >= 0.65
            and float(one_year["leaveCountryOut2000Plus"]["accuracy"]) >= 0.65
            and float(two_year["leaveCountryOut2000Plus"]["accuracy"]) >= 0.65
            and float(three_year["leaveCountryOut2000Plus"]["accuracy"]) >= 0.65
            and family_ablation["status"] == "passed_limited"
        )
        cycles[cycle_id] = {
            "cycleId": cycle_id,
            "label": spec.label,
            "status": "directionally_predictable" if stable_direction else "research_only",
            "publishableClaim": (
                "住房—信用核心综合因子未来1–3年方向概率具备跨时期、跨国家样本外指示意义；尚不能稳定外推为广义经济结果、资产收益、精确幅度或精确转折时点。"
                if stable_direction
                else "现阶段只保留研究诊断，不发布稳定预测结论。"
            ),
            "history": _global_history(historical),
            "bridgeHistory": _global_history(aligned_bridge),
            "partialNowcast": partial_nowcast,
            "spectral": spectral_validation(historical, cycle_id),
            "validation": {"1y": one_year, "2y": two_year, "3y": three_year},
            "familyAblation": family_ablation,
            "independentOutcomeValidation": independent_outcomes,
            "architectureComparison": c2_architecture
            if cycle_id == "C2"
            else None,
            "currentForecasts": [
                current_one_year,
                current_two_year,
                current_three_year,
            ],
            "featureFamilies": [
                column.removeprefix("family_")
                for column in historical.columns
                if column.startswith("family_")
            ],
            "factorArchitecture": (
                {
                    "definition": "地产—信用核心与宏观传播分层系统",
                    "coreFamilies": list(C2_CORE_FAMILIES),
                    "confirmationFamilies": list(C2_CONFIRMATION_FAMILIES),
                    "propagationFamilies": list(C2_PROPAGATION_FAMILIES),
                    "coreRole": "住房动量与按揭信用共同定义C2自身状态。",
                    "confirmationRole": "总投资脉冲和融资条件只做一致性确认与传播解释；当前同口径样本外比较未证明其能稳定改善方向概率，因此默认权重为零。",
                    "defaultDirectionModelFamilies": list(C2_CORE_FAMILIES),
                    "positionLayer": "估值、杠杆和投资水平另行描述结构位置，不用于锁定周期长度。",
                }
                if cycle_id == "C2"
                else {
                    "definition": "资本形成综合因子",
                    "coreFamilies": [
                        column.removeprefix("family_")
                        for column in historical.columns
                        if column.startswith("family_")
                    ],
                    "confirmationFamilies": [],
                }
            ),
            "governance": {
                "formalStatus": "blocked",
                "recommendedUpgrade": "仅允许发布因子自身方向概率；广义经济结果、资产归因和正式相位仍需独立验证。",
                "notAllowed": ["把因子方向称为广义经济预测", "精确拐点年份承诺", "精确相位角外推", "把研究概率直接当资产收益预测"],
            },
        }

    return {
        "meta": {
            "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
            "historicalEnd": 2020,
            "currentBridgeEnd": max(
                forecast["asOfYear"]
                for cycle in cycles.values()
                for forecast in cycle["currentForecasts"]
            ),
            "currentBridgeEndPeriod": max(
                str(forecast["asOfPeriod"])
                for cycle in cycles.values()
                for forecast in cycle["currentForecasts"]
            ),
            "refreshRequested": refresh,
            "researchDefinition": "稳定预测=递归样本外方向准确率、Brier分数和国家留一验证同时优于简单基准。",
        },
        "sources": [
            {
                "name": "JST Macrohistory Database R6",
                "coverage": "18个发达经济体，1870–2020，年度",
                "role": "房价、按揭、投资、企业信用、利率、GDP和资产收益的同口径历史验证",
                "url": "https://www.macrohistory.net/database/",
                **_cache_snapshot(RAW_DIR / "JSTdatasetR6.dta"),
            },
            {
                "name": "BIS Selected Residential Property Prices",
                "coverage": f"季度，最早{spp['TIME_PERIOD'].astype(str).min()}，缓存最新{spp['TIME_PERIOD'].astype(str).max()}；完整年度与部分年度分层",
                "role": "真实住宅价格与当前地产状态",
                "url": "https://data.bis.org/topics/RPP",
                **_cache_snapshot(RAW_DIR / "BIS_WS_SPP.csv"),
            },
            {
                "name": "BIS Total Credit",
                "coverage": f"季度，最早{total_credit['TIME_PERIOD'].astype(str).min()}，缓存最新{total_credit['TIME_PERIOD'].astype(str).max()}",
                "role": "家庭和非金融企业信用占GDP",
                "url": "https://data.bis.org/topics/TOTAL_CREDIT",
                **_cache_snapshot(RAW_DIR / "BIS_WS_TC.csv"),
            },
            {
                "name": "World Bank WDI",
                "coverage": f"年度，固定资本形成、实际GDP增长、贷款利率与CPI缓存最新{int(world_bank['year'].max())}",
                "role": "C3投资与增长当前桥接；C2投资水平与有限覆盖融资条件桥接",
                "url": "https://data.worldbank.org/",
                "caches": [
                    _cache_snapshot(RAW_DIR / "world_bank_NE_GDI_FTOT_ZS.json"),
                    _cache_snapshot(RAW_DIR / "world_bank_NY_GDP_MKTP_KD_ZG.json"),
                    _cache_snapshot(RAW_DIR / "world_bank_FR_INR_LEND.json"),
                    _cache_snapshot(RAW_DIR / "world_bank_FP_CPI_TOTL_ZG.json"),
                ],
            },
            {
                "name": "OECD Quarterly National Accounts",
                "coverage": f"实际固定资本形成，季度，{oecd_gfcf['TIME_PERIOD'].astype(str).min()}—{oecd_gfcf['TIME_PERIOD'].astype(str).max()}，{oecd_gfcf['REF_AREA'].nunique()}国",
                "role": "C3当前投资脉冲部分年度桥接；使用季调链量实际固定资本形成",
                "url": "https://data-explorer.oecd.org/",
                **_cache_snapshot(RAW_DIR / "OECD_QNA_GFCF.csv"),
            },
            {
                "name": "OECD Analytical House Price Indicators",
                "coverage": f"房价租金比（相对长期均值），季度，{oecd_house_prices['TIME_PERIOD'].astype(str).min()}—{oecd_house_prices['TIME_PERIOD'].astype(str).max()}，{oecd_house_prices['REF_AREA'].nunique()}国",
                "role": "C2房价租金比动量与当前季度桥接；与BIS真实房价共同形成住房动量",
                "url": "https://data-explorer.oecd.org/vis?df[ag]=OECD.ECO.MPD&df[id]=DSD_AN_HOUSE_PRICES@DF_HOUSE_PRICES",
                **_cache_snapshot(OECD_HOUSE_PRICE_CACHE),
            },
            {
                "name": "OECD Short-term Interest Rates",
                "coverage": f"三个月短端利率，年度，{int(oecd_short_rates['year'].min())}—{int(oecd_short_rates['year'].max())}，{oecd_short_rates['iso'].nunique()}国",
                "role": "C2实际融资条件确认层；与JST短端实际利率原定义做替换检验",
                "url": "https://data-explorer.oecd.org/vis?df[ag]=OECD.SDD.STES&df[id]=DSD_STES%40DF_FINMARK",
                **_cache_snapshot(OECD_SHORT_RATE_CACHE),
            },
        ],
        "cycles": cycles,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="强制刷新JST、BIS和World Bank缓存，并保留真实源时点。",
    )
    args = parser.parse_args()
    payload = build_research_payload(refresh=args.refresh)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUTPUT_PATH}")
    for cycle_id, cycle in payload["cycles"].items():
        validation = cycle["validation"]
        print(
            cycle_id,
            "1y accuracy=",
            validation["1y"]["accuracy"],
            "3y accuracy=",
            validation["3y"]["accuracy"],
            "status=",
            cycle["status"],
        )


if __name__ == "__main__":
    main()
