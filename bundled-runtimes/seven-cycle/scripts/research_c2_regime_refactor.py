"""Build the refactored C2 regime, expert calibration, and joint asset mapping."""

from __future__ import annotations

from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from seven_cycle_platform.assets import (
    build_c2_asset_exposure_registry,
    build_weighted_c2_features,
)
from seven_cycle_platform.cycles.c2_regime import (
    bis_area_code,
    build_c2_historical_dating,
    build_direct_c2_state,
    date_c2_turning_points,
    estimate_c2_lead_lag,
    future_transition_target,
)

try:
    from scripts.research_c2_c3_historical_mapping import (
        C2_GEOGRAPHIC_REGIONS,
        C2_ISO_REGION,
        build_asset_mapping,
        build_asset_universe,
        build_c2_geographic_asset_validation,
    )
    from scripts.research_c2_c3_long_panel import (
        _align_bridge_factor,
        _fetch_bis,
        _fetch_oecd_house_prices,
        _fetch_oecd_short_rates,
        _fetch_world_bank,
        _jst_country_features,
        _load_jst,
        build_bridge_panel,
        build_c2_partial_year_panel,
        build_jst_panel,
        causal_robust_z,
    )
except ModuleNotFoundError:
    from research_c2_c3_historical_mapping import (  # type: ignore[no-redef]
        C2_GEOGRAPHIC_REGIONS,
        C2_ISO_REGION,
        build_asset_mapping,
        build_asset_universe,
        build_c2_geographic_asset_validation,
    )
    from research_c2_c3_long_panel import (  # type: ignore[no-redef]
        _align_bridge_factor,
        _fetch_bis,
        _fetch_oecd_house_prices,
        _fetch_oecd_short_rates,
        _fetch_world_bank,
        _jst_country_features,
        _load_jst,
        build_bridge_panel,
        build_c2_partial_year_panel,
        build_jst_panel,
        causal_robust_z,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "output" / "c2_regime_refactor.json"
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
MAPPING_PATH = PROJECT_ROOT / "output" / "c2_c3_historical_mapping.json"
C1_PATH = PROJECT_ROOT / "output" / "c1_long_wave_validation.json"
C4_PATH = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
C5_PATH = PROJECT_ROOT / "output" / "c5_liquidity_state_research.json"
C7_PATH = PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json"
C2_EXPOSURE_PATH = (
    PROJECT_ROOT / "config" / "seven_cycle" / "c2_asset_exposures.yaml"
)

C2_FOCUS_COUNTRIES = {
    "CHN": "中国",
    "USA": "美国",
    "JPN": "日本",
    "GBR": "英国",
}
C2_DIRECT_REGIONS = {
    **C2_GEOGRAPHIC_REGIONS,
    "china": {
        "label": "中国",
        "isos": ("CHN",),
        "minimumCountries": 1,
    },
}
C2_FEATURE_COLUMNS = (
    "C2",
    "C2_slope",
    "C2_consensus",
    "C2_phase_recovery",
    "C2_phase_expansion",
    "C2_phase_slowdown",
)
C2_EVENT_ASSET_CATEGORIES = ("跨国股票", "跨国国债", "跨国短票")
C2_EVENT_HORIZONS = (1, 3)
C2_EVENT_TARGETS = ("return", "risk")
C2_ASSET_PERSISTENCE_COLUMNS = (
    "assetReturn",
    "assetMomentum3",
    "assetRisk3",
    "assetRisk5",
)
C2_ASYMMETRIC_PRESSURE_COLUMNS = (
    "positivePressure",
    "boomReversal",
    "leverageReversal",
    "leverageTightening",
    "synchronizedDownturn",
)
C2_MACRO_PRESSURE_COLUMNS = (
    "positivePressure",
    "boomReversal",
    "leverageReversal",
    "synchronizedDownturn",
)
C2_RISK_PARAMETER_GRID = (0.01, 0.03, 0.10, 0.30)
C2_RISK_ARCHITECTURES = {
    "asset_persistence": C2_ASSET_PERSISTENCE_COLUMNS,
    "global_common": (
        *C2_ASSET_PERSISTENCE_COLUMNS,
        "globalActivity",
        "globalSlope",
    ),
    "country_hierarchy": (
        *C2_ASSET_PERSISTENCE_COLUMNS,
        "globalActivity",
        "globalSlope",
        "countryDeviation",
        "countryDeviationSlope",
        "mortgageCredit",
        "financingConditions",
        "deviationFinancingInteraction",
        "creditFinancingInteraction",
    ),
    "asymmetric_pressure": (
        *C2_ASSET_PERSISTENCE_COLUMNS,
        *C2_ASYMMETRIC_PRESSURE_COLUMNS,
    ),
}
C2_ASSET_CLASS_TARGETS = {
    "跨国股票": (
        {
            "targetId": "real_return_direction",
            "label": "实际收益方向",
            "valueColumn": "forwardReturn",
            "labelMode": "positive",
            "definition": "未来期限累计实际总收益是否大于零。",
        },
        {
            "targetId": "maximum_drawdown",
            "label": "最大回撤高风险",
            "valueColumn": "forwardMaxDrawdown",
            "labelMode": "upper_quartile",
            "definition": "未来期限累计路径最大回撤是否进入该国股票自身历史75%高位。",
        },
    ),
    "跨国国债": (
        {
            "targetId": "real_return_direction",
            "label": "实际收益方向",
            "valueColumn": "forwardReturn",
            "labelMode": "positive",
            "definition": "未来期限累计实际国债总收益是否大于零。",
        },
        {
            "targetId": "downside_loss",
            "label": "下行损失高风险",
            "valueColumn": "forwardRisk",
            "labelMode": "upper_quartile",
            "definition": "未来期限负收益均方根是否进入该国国债自身历史75%高位。",
        },
    ),
    "跨国短票": (
        {
            "targetId": "real_return_direction",
            "label": "实际短端收益方向",
            "valueColumn": "forwardReturn",
            "labelMode": "positive",
            "definition": "未来期限累计实际短票收益是否大于零。",
        },
        {
            "targetId": "real_rate_shock",
            "label": "实际利率冲击",
            "valueColumn": "forwardRateShock",
            "labelMode": "upper_quartile",
            "definition": "未来期限实际短端收益率最大年度变动是否进入该国自身历史75%高位。",
        },
    ),
}
C2_ASSET_CLASS_BASELINES = {
    "跨国股票": C2_ASSET_PERSISTENCE_COLUMNS,
    "跨国国债": (
        *C2_ASSET_PERSISTENCE_COLUMNS,
        "realShortRate",
        "realLongRate",
        "yieldCurve",
        "shortRateChange",
        "longRateChange",
    ),
    "跨国短票": (
        "assetReturn",
        "assetMomentum3",
        "assetChange1",
        "assetChange3",
        "realShortRate",
        "shortRateChange",
        "yieldCurve",
    ),
}
C2_ASSET_CLASS_INCREMENTS = {
    "跨国股票": (
        "globalActivity",
        "globalSlope",
        "countryDeviation",
        "countryDeviationSlope",
        "mortgageCredit",
        "positivePressure",
        "boomReversal",
        "synchronizedDownturn",
    ),
    "跨国国债": (
        "globalActivity",
        "globalSlope",
        "countryDeviation",
        "countryDeviationSlope",
        "mortgageCredit",
        "financingConditions",
        "positivePressure",
        "boomReversal",
        "leverageReversal",
        "synchronizedDownturn",
        "c2RealRateInteraction",
        "pressureRealRateInteraction",
    ),
    "跨国短票": (
        "globalActivity",
        "globalSlope",
        "countryDeviation",
        "countryDeviationSlope",
        "mortgageCredit",
        "financingConditions",
        "creditFinancingInteraction",
        "c2RealRateInteraction",
    ),
}
C2_CONDITIONAL_PROPAGATION_SCENARIOS = (
    {
        "scenarioId": "high_leverage_financing_easing",
        "label": "高杠杆后融资转松",
        "column": "scenarioHighLeverageEasing",
        "definition": "上一年结构压力为正，且当前三年实际短端融资条件边际转松；信号为两者正值乘积。",
    },
    {
        "scenarioId": "housing_downturn_recession",
        "label": "地产下行叠加经济衰退",
        "column": "scenarioDownturnRecession",
        "definition": "当前住房动量为负，且当期实际人均GDP增长低于自身历史趋势；信号为两项下行幅度乘积。",
    },
    {
        "scenarioId": "housing_recovery_credit_expansion",
        "label": "住房复苏叠加信用扩张",
        "column": "scenarioRecoveryCreditExpansion",
        "definition": "上一年C2活动核心低于趋势，当前住房动量转正且按揭信用扩张；信号为三项正值乘积。",
    },
)


def _json_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        return None if not math.isfinite(float(value)) else round(float(value), 6)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return [
        {key: _json_value(value) for key, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]


def _global_factor(panel: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    pivot = panel.pivot_table(index="year", columns="iso", values="factor", aggfunc="last")
    count = pivot.notna().sum(axis=1)
    factor = pivot.median(axis=1, skipna=True).where(count >= 6).dropna()
    return factor, count.reindex(factor.index).astype(int)


def _global_family_states(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    states: dict[str, pd.DataFrame] = {}
    for column in sorted(
        item for item in panel.columns if item.startswith("family_")
    ):
        pivot = panel.pivot_table(
            index="year",
            columns="iso",
            values=column,
            aggfunc="last",
        )
        count = pivot.notna().sum(axis=1)
        factor = pivot.median(axis=1, skipna=True).where(count >= 6).dropna()
        if len(factor) < 20:
            continue
        state = build_direct_c2_state(factor)
        state["countryCount"] = count.reindex(factor.index).astype(int)
        states[column.removeprefix("family_")] = state
    return states


def _family_state_summary(
    family_states: dict[str, pd.DataFrame],
    *,
    as_of_year: int,
) -> dict[str, object]:
    roles = {
        "housing_momentum": "core",
        "mortgage_credit": "core",
        "investment_confirmation": "confirmation",
        "financing_conditions": "confirmation",
    }
    labels = {
        "housing_momentum": "住房动量",
        "mortgage_credit": "按揭信用",
        "investment_confirmation": "投资确认",
        "financing_conditions": "融资条件",
    }
    rows: list[dict[str, object]] = []
    for family_id, state in family_states.items():
        latest = state.iloc[-1]
        latest_year = int(state.index[-1])
        rows.append(
            {
                "familyId": family_id,
                "label": labels.get(family_id, family_id),
                "role": roles.get(family_id, "propagation"),
                "year": latest_year,
                "lagYears": max(0, as_of_year - latest_year),
                "currentEligible": latest_year >= as_of_year - 1,
                "activity": _json_value(latest["activity"]),
                "phase": str(latest["phase"]),
                "rawPhase": str(latest["rawPhase"]),
                "slopeConsensus": _json_value(latest["slopeConsensus"]),
                "slopeDirection": int(latest["slopeDirection"]),
                "countryCount": int(latest["countryCount"]),
            }
        )
    eligible_core = [
        row
        for row in rows
        if row["role"] == "core" and row["currentEligible"]
    ]
    positive_core = [
        row for row in eligible_core if int(row["slopeDirection"]) > 0
    ]
    return {
        "status": "available" if len(eligible_core) == 2 else "partial",
        "coreRecoveryShare": _json_value(
            len(positive_core) / len(eligible_core) if eligible_core else None
        ),
        "coreFamilyCount": len(eligible_core),
        "families": rows,
        "method": "住房动量、按揭信用、投资和融资条件各自独立形成状态；核心家族决定转相，确认层只加减置信度。",
    }


def _transition_evidence(
    state: pd.DataFrame,
    family_summary: dict[str, object],
    geographic_state: dict[str, object],
) -> dict[str, object]:
    latest = state.iloc[-1]
    current_phase = str(latest["phase"])
    candidate_phase = str(latest["rawPhase"])
    global_signal = candidate_phase != current_phase
    families = family_summary["families"]
    eligible_core = [
        row
        for row in families
        if row["role"] == "core" and row["currentEligible"]
    ]
    core_support = (
        float(np.mean([int(row["slopeDirection"]) > 0 for row in eligible_core]))
        if eligible_core
        else 0.0
    )
    current_countries = geographic_state["currentCountries"]
    country_recovery_share = float(
        np.mean(
            [
                row["phase"] in {"recovery", "expansion"}
                for row in current_countries
            ]
        )
    )
    current_regions = geographic_state["currentRegions"]
    region_recovery_share = float(
        np.mean(
            [
                row["phase"] in {"recovery", "expansion"}
                for row in current_regions
            ]
        )
    )
    confirmation_rows = [
        row
        for row in families
        if row["role"] == "confirmation" and row["currentEligible"]
    ]
    confirmation_support = (
        float(
            np.mean(
                [int(row["slopeDirection"]) > 0 for row in confirmation_rows]
            )
        )
        if confirmation_rows
        else 0.0
    )
    score = (
        0.35 * float(global_signal)
        + 0.30 * core_support
        + 0.20 * country_recovery_share
        + 0.10 * region_recovery_share
        + 0.05 * confirmation_support
    )
    required = 0.65
    candidate = bool(global_signal and core_support >= 0.50 and score >= required)
    return {
        "status": "candidate" if candidate else "not_confirmed",
        "fromPhase": current_phase,
        "candidatePhase": candidate_phase if global_signal else None,
        "score": _json_value(score),
        "requiredScore": required,
        "components": {
            "globalRawTransition": _json_value(float(global_signal)),
            "coreFamilySupport": _json_value(core_support),
            "countryRecoveryShare": _json_value(country_recovery_share),
            "regionRecoveryShare": _json_value(region_recovery_share),
            "confirmationSupport": _json_value(confirmation_support),
        },
        "method": "只有全球直接状态先出现候选，且住房、按揭、国家广度与区域广度共同支持时，才允许进入转相候选；随后仍需连续两期确认。",
    }


def _quarterly_country_c2_state(
    spp: pd.DataFrame,
    total_credit: pd.DataFrame,
    *,
    iso: str,
) -> pd.DataFrame:
    area = bis_area_code(iso)
    house = spp.loc[
        (spp["REF_AREA"].astype(str) == area)
        & (spp["VALUE"] == "R")
        & (pd.to_numeric(spp["UNIT_MEASURE"], errors="coerce") == 628),
        ["TIME_PERIOD", "OBS_VALUE"],
    ].copy()
    credit = total_credit.loc[
        (total_credit["BORROWERS_CTY"].astype(str) == area)
        & (total_credit["TC_LENDERS"] == "A")
        & (total_credit["VALUATION"] == "M")
        & (total_credit["UNIT_TYPE"].astype(str) == "770")
        & (total_credit["TC_ADJUST"] == "A")
        & (total_credit["UNIT_MEASURE"].astype(str) == "367")
        & (total_credit["TC_BORROWERS"] == "H"),
        ["TIME_PERIOD", "OBS_VALUE"],
    ].copy()
    house["date"] = pd.PeriodIndex(house["TIME_PERIOD"], freq="Q").to_timestamp("Q")
    credit["date"] = pd.PeriodIndex(credit["TIME_PERIOD"], freq="Q").to_timestamp("Q")
    house_values = pd.Series(
        pd.to_numeric(house["OBS_VALUE"], errors="coerce").to_numpy(),
        index=house["date"],
    ).sort_index()
    credit_values = pd.Series(
        pd.to_numeric(credit["OBS_VALUE"], errors="coerce").to_numpy(),
        index=credit["date"],
    ).sort_index()
    credit_values = credit_values.reindex(
        house_values.index.union(credit_values.index)
    ).sort_index().ffill(limit=1)
    core = pd.concat(
        {
            "housingMomentum": causal_robust_z(
                np.log(house_values.where(house_values > 0)).diff(12) / 3.0,
                window=40,
                min_periods=16,
            ),
            "mortgageCredit": causal_robust_z(
                credit_values.diff(12) / 3.0,
                window=40,
                min_periods=16,
            ),
        },
        axis=1,
    )
    activity = core.mean(axis=1, skipna=True).where(core.notna().sum(axis=1) >= 2)
    state = build_direct_c2_state(
        activity.dropna(),
        minimum_history=8,
        momentum_windows=(4, 8, 12),
    ).reset_index(names="date")
    state = state.rename(
        columns={
            "slope4Y": "slope1Y",
            "slope8Y": "slope2Y",
            "slope12Y": "slope3Y",
        }
    )
    state["slope"] = state["slope"] * 4.0
    state["phaseDurationYears"] = (
        state["phaseDurationYears"] / 4.0
    ).round(2)
    state["iso"] = iso
    state["regionId"] = "china" if iso == "CHN" else C2_ISO_REGION[iso]
    state["year"] = pd.DatetimeIndex(state["date"]).year
    state["asOfPeriod"] = pd.PeriodIndex(state["date"], freq="Q").astype(str)
    return state


def _combined_c2_panel() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, object],
    dict[str, pd.DataFrame],
    pd.DataFrame,
    pd.DataFrame,
]:
    jst = _load_jst()
    spp, total_credit = _fetch_bis()
    world_bank = _fetch_world_bank()
    oecd_house_prices = _fetch_oecd_house_prices()
    oecd_short_rates = _fetch_oecd_short_rates()
    historical = build_jst_panel(jst, "C2")
    bridge = build_bridge_panel(
        "C2",
        spp=spp,
        total_credit=total_credit,
        world_bank=world_bank,
        oecd_house_prices=oecd_house_prices,
        oecd_short_rates=oecd_short_rates,
    )
    partial, metadata = build_c2_partial_year_panel(
        bridge,
        spp,
        oecd_house_prices,
    )
    aligned = _align_bridge_factor(historical, partial)
    historical_factor, historical_count = _global_factor(historical)
    bridge_factor, bridge_count = _global_factor(aligned)
    extension = bridge_factor.loc[bridge_factor.index > historical_factor.index.max()]
    combined_panel = pd.concat(
        [
            historical.loc[
                historical["year"] <= historical_factor.index.max()
            ],
            aligned.loc[aligned["year"] > historical_factor.index.max()],
            aligned.loc[~aligned["iso"].isin(historical["iso"].unique())],
        ],
        ignore_index=True,
        sort=False,
    ).drop_duplicates(["iso", "year"], keep="last")
    factor = pd.concat([historical_factor, extension]).sort_index()
    count = pd.concat(
        [historical_count, bridge_count.reindex(extension.index)]
    ).reindex(factor.index)
    state = build_direct_c2_state(factor)
    state["countryCount"] = count
    quarterly_states = {
        iso: _quarterly_country_c2_state(spp, total_credit, iso=iso)
        for iso in C2_FOCUS_COUNTRIES
    }
    return (
        jst,
        state,
        combined_panel,
        metadata,
        quarterly_states,
        historical,
        bridge,
    )


def _direct_geographic_state(
    panel: pd.DataFrame,
    global_state: pd.DataFrame,
    quarterly_states: dict[str, pd.DataFrame],
) -> tuple[dict[str, object], pd.DataFrame, pd.DataFrame]:
    country_rows: list[pd.DataFrame] = []
    annual_country_isos: set[str] = set()
    for iso, country in panel.groupby("iso"):
        iso = str(iso)
        factor = (
            country.sort_values("year")
            .drop_duplicates("year", keep="last")
            .set_index("year")["factor"]
            .dropna()
        )
        region_id = C2_ISO_REGION.get(iso)
        minimum_history = 60
        if len(factor) < minimum_history or region_id is None:
            continue
        state = build_direct_c2_state(factor).reset_index(names="year")
        state["iso"] = iso
        state["regionId"] = region_id
        country_rows.append(state)
        annual_country_isos.add(iso)
    for iso, state in quarterly_states.items():
        if iso in annual_country_isos:
            continue
        country_rows.append(
            state.sort_values("date").groupby("year", as_index=False).tail(1)
        )
    country_history = pd.concat(country_rows, ignore_index=True)

    region_rows: list[pd.DataFrame] = []
    for region_id, specification in C2_DIRECT_REGIONS.items():
        if region_id == "china" and "CHN" in quarterly_states:
            state = (
                quarterly_states["CHN"]
                .sort_values("date")
                .groupby("year", as_index=False)
                .tail(1)
                .copy()
            )
            state["regionId"] = region_id
            state["regionLabel"] = str(specification["label"])
            state["countryCount"] = 1
            region_rows.append(state)
            continue
        pivot = panel.loc[panel["iso"].isin(specification["isos"])].pivot_table(
            index="year",
            columns="iso",
            values="factor",
            aggfunc="last",
        )
        count = pivot.notna().sum(axis=1)
        factor = pivot.median(axis=1, skipna=True).where(
            count >= int(specification["minimumCountries"])
        ).dropna()
        state = build_direct_c2_state(factor).reset_index(names="year")
        state["regionId"] = region_id
        state["regionLabel"] = str(specification["label"])
        state["countryCount"] = count.reindex(factor.index).to_numpy()
        region_rows.append(state)
    region_history = pd.concat(region_rows, ignore_index=True)

    current_countries = (
        country_history.sort_values(["iso", "year"])
        .groupby("iso", as_index=False)
        .tail(1)
    )
    quarterly_current = pd.concat(
        [
            state.sort_values("date").tail(1)
            for state in quarterly_states.values()
        ],
        ignore_index=True,
    )
    current_countries = pd.concat(
        [
            current_countries.loc[
                ~current_countries["iso"].isin(quarterly_states)
            ],
            quarterly_current,
        ],
        ignore_index=True,
        sort=False,
    )
    current_regions = (
        region_history.sort_values(["regionId", "year"])
        .groupby("regionId", as_index=False)
        .tail(1)
    )
    global_current = global_state.iloc[-1]
    global_phase = str(global_current["phase"])
    global_slope = int(global_current["slopeDirection"])
    global_by_year = global_state[["phase", "slopeDirection"]].copy()
    country_breadth = (
        country_history.merge(
            global_by_year.reset_index(names="year"),
            on="year",
            how="inner",
            suffixes=("", "Global"),
        )
        .assign(
            phaseAgree=lambda frame: frame["phase"] == frame["phaseGlobal"],
            slopeAgree=lambda frame: frame["slopeDirection"]
            == frame["slopeDirectionGlobal"],
        )
        .groupby("year")
        .agg(
            countryCount=("iso", "nunique"),
            phaseAgreement=("phaseAgree", "mean"),
            slopeAgreement=("slopeAgree", "mean"),
        )
        .reset_index()
    )
    focus_countries: list[dict[str, object]] = []
    panel_pivot = panel.pivot_table(
        index="year",
        columns="iso",
        values="factor",
        aggfunc="last",
    )
    quarterly_annual = pd.concat(
        {
            iso: state.set_index("date")["activity"].resample("YE").last()
            for iso, state in quarterly_states.items()
        },
        axis=1,
    )
    quarterly_annual.index = quarterly_annual.index.year
    for iso, label in C2_FOCUS_COUNTRIES.items():
        history = current_countries.loc[current_countries["iso"] == iso]
        if history.empty or (iso not in panel_pivot and iso not in quarterly_states):
            continue
        country_factor = quarterly_annual[iso].dropna()
        peer_panel = quarterly_annual.drop(columns=[iso], errors="ignore")
        peer_count = peer_panel.notna().sum(axis=1)
        peer_factor = peer_panel.median(
            axis=1,
            skipna=True,
        ).where(peer_count >= 2)
        lag = estimate_c2_lead_lag(
            country_factor,
            peer_factor,
            maximum_lag_years=3 if iso == "CHN" else 5,
            minimum_overlap=12 if iso == "CHN" else 30,
        )
        latest_country = history.iloc[-1]
        peer_latest = peer_factor.reindex([int(latest_country["year"])]).iloc[0]
        observations = int(len(quarterly_states[iso]))
        focus_countries.append(
            {
                "iso": iso,
                "name": label,
                "regionId": str(latest_country["regionId"]),
                "startYear": int(
                    quarterly_states[iso]["year"].min()
                    if iso in quarterly_states
                    else country_factor.index.min()
                ),
                "asOfYear": int(latest_country["year"]),
                "asOfPeriod": str(
                    quarterly_states[iso].iloc[-1]["asOfPeriod"]
                ),
                "observations": observations,
                "historyTier": "modern_quarterly_short"
                if len(quarterly_states[iso]) < 80
                else "modern_quarterly_direct",
                "phase": str(latest_country["phase"]),
                "activity": _json_value(latest_country["activity"]),
                "slopeConsensus": _json_value(latest_country["slopeConsensus"]),
                "phaseDurationYears": _json_value(
                    latest_country["phaseDurationYears"]
                ),
                "deviationFromPeers": _json_value(
                    float(latest_country["activity"]) - float(peer_latest)
                    if np.isfinite(peer_latest)
                    else None
                ),
                "leadLagVsPeers": {
                    "leadYears": lag["leadYears"],
                    "observations": lag["observations"],
                    "correlation": _json_value(lag["correlation"]),
                    "simultaneousCorrelation": _json_value(
                        lag["simultaneousCorrelation"]
                    ),
                    "correlationImprovement": _json_value(
                        lag["correlationImprovement"]
                    ),
                    "materialLag": bool(lag["materialLag"]),
                    "status": "exploratory"
                    if len(country_factor) < 20
                    else "historical_diagnostic",
                },
            }
        )
    return (
        {
            "status": "research_only",
            "globalPhase": global_phase,
            "globalSlopeDirection": global_slope,
            "summary": {
                "countryCount": int(len(current_countries)),
                "regionCount": int(len(current_regions)),
                "countryPhaseAgreementWithGlobal": _json_value(
                    (current_countries["phase"] == global_phase).mean()
                ),
                "countrySlopeAgreementWithGlobal": _json_value(
                    (current_countries["slopeDirection"] == global_slope).mean()
                ),
                "regionPhaseAgreementWithGlobal": _json_value(
                    (current_regions["phase"] == global_phase).mean()
                ),
                "regionSlopeAgreementWithGlobal": _json_value(
                    (current_regions["slopeDirection"] == global_slope).mean()
                ),
                "focusCountryCount": len(focus_countries),
            },
            "currentCountries": _records(
                current_countries[
                    [
                        "iso",
                        "regionId",
                        "year",
                        "phase",
                        "rawPhase",
                        "activity",
                        "slopeConsensus",
                        "phaseDurationYears",
                    ]
                ]
            ),
            "currentRegions": _records(
                current_regions[
                    [
                        "regionId",
                        "regionLabel",
                        "year",
                        "phase",
                        "rawPhase",
                        "activity",
                        "slopeConsensus",
                        "phaseDurationYears",
                        "countryCount",
                    ]
                ]
            ),
            "breadthHistory": _records(country_breadth),
            "focusCountries": focus_countries,
            "method": "各国先独立形成住房—按揭活动核心，再拆为全球共同项、区域项和本国偏离项；领先滞后只对本国与剔除本国后的全球同业轨道比较，避免本国数据机械抬高相关性。",
            "caveat": "四个重点国家均使用BIS季度住房—家庭信用直接轨道；中国仅有2012年后的有效双核心样本，单独标为短样本。国家错位尚未通过资产样本外门槛，不直接转换为收益、风险或配置建议。",
        },
        country_history,
        region_history,
    )


def _turning_point_validation(
    jst: pd.DataFrame,
    turning_points: list[dict[str, object]],
) -> dict[str, object]:
    crisis = (
        jst.assign(
            crisis=pd.to_numeric(jst["crisisJST"], errors="coerce").fillna(0.0)
        )
        .groupby("year")["crisis"]
        .sum()
    )
    systemic_years = [int(year) for year, value in crisis.items() if value >= 2]
    peak_years = [
        int(turn["year"]) for turn in turning_points if turn["kind"] == "peak"
    ]
    matched_crises: list[dict[str, object]] = []
    for year in systemic_years:
        candidates = [peak for peak in peak_years if year - 5 <= peak <= year + 1]
        if not candidates:
            continue
        closest = min(candidates, key=lambda peak: abs(peak - year))
        matched_crises.append(
            {"crisisYear": year, "peakYear": closest, "leadYears": year - closest}
        )
    matched_peaks = {int(row["peakYear"]) for row in matched_crises}
    return {
        "status": "historical_calibration_only",
        "benchmark": "JST银行危机年份中至少两个样本国同时进入危机",
        "systemicCrisisYears": systemic_years,
        "matchedCrises": matched_crises,
        "crisisCoverage": _json_value(len(matched_crises) / len(systemic_years)),
        "peakPrecision": _json_value(
            len(matched_peaks) / len(peak_years) if peak_years else None
        ),
        "medianLeadYears": _json_value(
            np.median([row["leadYears"] for row in matched_crises])
            if matched_crises
            else None
        ),
        "method": "先用多参数滤波共识独立识别历史峰值，再用银行危机日期做外部核验；危机日期不参与拟合，也不用于手工移动峰谷。",
        "caveat": "峰值精度只在少量共识峰值上计算，不能单独宣传；银行危机也只覆盖地产—信用周期的一部分尾部结果。",
    }


def _country_risk_panel(jst: pd.DataFrame) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for iso, group in jst.groupby("iso"):
        country = group.sort_values("year").set_index("year")
        features = _jst_country_features(group, "C2")
        nominal_gdp = pd.to_numeric(country["gdp"], errors="coerce").where(
            lambda value: value > 0
        )
        rental_yield = pd.to_numeric(
            country["housing_rent_yd"], errors="coerce"
        ).where(lambda value: value > 0)
        pressure = pd.concat(
            [
                causal_robust_z(-np.log(rental_yield)),
                causal_robust_z(
                    pd.to_numeric(country["tmort"], errors="coerce") / nominal_gdp
                ),
                causal_robust_z(pd.to_numeric(country["iy"], errors="coerce")),
            ],
            axis=1,
        ).mean(axis=1, skipna=True)
        activity = (
            features[["housing_momentum", "mortgage_credit"]]
            .mean(axis=1, skipna=True)
            .where(
                features[["housing_momentum", "mortgage_credit"]]
                .notna()
                .sum(axis=1)
                >= 2
            )
            .ewm(span=5, adjust=False, min_periods=2)
            .mean()
        )
        confirmation = features[
            ["investment_confirmation", "financing_conditions"]
        ].mean(axis=1, skipna=True)
        frame = pd.DataFrame(
            {
                "iso": iso,
                "year": country.index,
                "activity": activity,
                "activitySlope": activity.diff(),
                "pressure": pressure,
                "confirmation": confirmation,
                "crisis": pd.to_numeric(
                    country["crisisJST"], errors="coerce"
                ).fillna(0.0),
            }
        )
        rows.append(frame.reset_index(drop=True))
    return pd.concat(rows, ignore_index=True)


def _risk_validation(panel: pd.DataFrame, horizon: int) -> dict[str, object]:
    target = pd.Series(index=panel.index, dtype="float64")
    for _, country in panel.groupby("iso"):
        future = pd.concat(
            [country["crisis"].shift(-step) for step in range(1, horizon + 1)],
            axis=1,
        )
        target.loc[country.index] = future.max(axis=1).where(
            future.notna().all(axis=1)
        )
    frame = panel.assign(target=target).dropna(subset=["target"])
    architectures = {
        "activity_only": ["activity", "activitySlope"],
        "activity_plus_pressure": ["activity", "activitySlope", "pressure"],
        "full_layered": [
            "activity",
            "activitySlope",
            "pressure",
            "confirmation",
        ],
    }
    results: dict[str, object] = {}
    for architecture, columns in architectures.items():
        actual: list[int] = []
        probabilities: list[float] = []
        base_probabilities: list[float] = []
        for year in sorted(frame["year"].unique()):
            if year < 1920:
                continue
            train = frame.loc[frame["year"] <= year - horizon]
            test = frame.loc[frame["year"] == year]
            if len(train) < 300 or test.empty or train["target"].nunique() < 2:
                continue
            model = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                LogisticRegression(C=0.05, max_iter=2_000),
            )
            model.fit(train[columns], train["target"].astype(int))
            probabilities.extend(model.predict_proba(test[columns])[:, 1].tolist())
            actual.extend(test["target"].astype(int).tolist())
            base_probabilities.extend([float(train["target"].mean())] * len(test))
        actual_array = np.asarray(actual)
        probability_array = np.asarray(probabilities)
        baseline_array = np.asarray(base_probabilities)
        results[architecture] = {
            "observations": int(len(actual_array)),
            "events": int(actual_array.sum()),
            "auc": _json_value(roc_auc_score(actual_array, probability_array)),
            "averagePrecision": _json_value(
                average_precision_score(actual_array, probability_array)
            ),
            "eventRate": _json_value(actual_array.mean()),
            "brier": _json_value(brier_score_loss(actual_array, probability_array)),
            "baseBrier": _json_value(brier_score_loss(actual_array, baseline_array)),
        }
    return {
        "horizonYears": horizon,
        "architectures": results,
        "selectedArchitecture": "full_layered",
        "interpretation": "结构压力和确认层只用于尾部风险揭示，不进入C2活动相位；当前危机增量较弱，因此不能输出精确危机概率。",
    }


def _annual_forward_target_values(
    asset: pd.DataFrame,
    *,
    horizon_years: int,
    target: str,
) -> dict[int, float]:
    returns = (
        asset.sort_values("year")
        .drop_duplicates("year", keep="last")
        .set_index("year")["return"]
        .astype(float)
    )
    values: dict[int, float] = {}
    for year in returns.index.astype(int):
        future = returns.reindex(range(year + 1, year + horizon_years + 1))
        if len(future) != horizon_years or future.isna().any():
            continue
        if target == "return":
            value = float(np.prod(1.0 + future.to_numpy()) - 1.0)
        else:
            downside = np.minimum(future.to_numpy(), 0.0)
            value = float(np.sqrt(np.mean(np.square(downside))))
        values[year] = value
    return values


def _annual_forward_path_values(
    asset: pd.DataFrame,
    *,
    horizon_years: int,
) -> dict[str, dict[int, float]]:
    returns = (
        asset.sort_values("year")
        .drop_duplicates("year", keep="last")
        .set_index("year")["return"]
        .astype(float)
    )
    result: dict[str, dict[int, float]] = {
        "forwardReturn": {},
        "forwardRisk": {},
        "forwardMaxDrawdown": {},
        "forwardRateShock": {},
    }
    for year in returns.index.astype(int):
        future = returns.reindex(range(year + 1, year + horizon_years + 1))
        if len(future) != horizon_years or future.isna().any():
            continue
        values = future.to_numpy(dtype="float64")
        cumulative = np.cumprod(1.0 + values)
        peaks = np.maximum.accumulate(np.concatenate(([1.0], cumulative)))[1:]
        drawdowns = cumulative / peaks - 1.0
        downside = np.minimum(values, 0.0)
        previous = float(returns.loc[year])
        result["forwardReturn"][year] = float(cumulative[-1] - 1.0)
        result["forwardRisk"][year] = float(
            np.sqrt(np.mean(np.square(downside)))
        )
        result["forwardMaxDrawdown"][year] = float(-np.min(drawdowns))
        result["forwardRateShock"][year] = float(
            np.max(np.abs(np.diff(np.concatenate(([previous], values)))))
        )
    return result


def _event_clock_statistics(
    asset: pd.DataFrame,
    turning_points: list[dict[str, object]],
    *,
    horizon_years: int,
    target: str,
) -> dict[str, object] | None:
    targets = _annual_forward_target_values(
        asset,
        horizon_years=horizon_years,
        target=target,
    )
    event_values: dict[str, list[float]] = {"peak": [], "trough": []}
    for turn in turning_points:
        year = int(turn["year"])
        value = targets.get(year)
        if value is not None and np.isfinite(value):
            event_values[str(turn["kind"])].append(value)
    if min(len(values) for values in event_values.values()) < 2:
        return None

    def summarize(values: list[float]) -> dict[str, object]:
        numeric = np.asarray(values, dtype="float64")
        return {
            "count": len(numeric),
            "mean": _json_value(np.mean(numeric)),
            "median": _json_value(np.median(numeric)),
            "positiveShare": _json_value(np.mean(numeric > 0.0)),
        }

    peak = summarize(event_values["peak"])
    trough = summarize(event_values["trough"])
    if target == "return":
        difference = float(trough["mean"]) - float(peak["mean"])
        difference_definition = "谷后收益减峰后收益"
    else:
        difference = float(peak["mean"]) - float(trough["mean"])
        difference_definition = "峰后风险减谷后风险"
    return {
        "peak": peak,
        "trough": trough,
        "eventDifference": _json_value(difference),
        "differenceDefinition": difference_definition,
    }


def _current_phase_asset_statistics(
    asset: pd.DataFrame,
    phase_history: pd.DataFrame,
    *,
    current_phase: str,
    horizon_years: int,
) -> dict[str, object] | None:
    frame = (
        asset[["year", "return"]]
        .merge(
            phase_history[["year", "phase"]].drop_duplicates("year", keep="last"),
            on="year",
            how="inner",
        )
        .sort_values("year")
    )
    frame["forwardReturn"] = frame["year"].map(
        _annual_forward_target_values(
            frame,
            horizon_years=horizon_years,
            target="return",
        )
    )
    frame["forwardRisk"] = frame["year"].map(
        _annual_forward_target_values(
            frame,
            horizon_years=horizon_years,
            target="risk",
        )
    )
    conditional = frame.loc[frame["phase"] == current_phase]
    conditional_return = conditional["forwardReturn"].dropna()
    conditional_risk = conditional["forwardRisk"].dropna()
    unconditional_return = frame["forwardReturn"].dropna()
    unconditional_risk = frame["forwardRisk"].dropna()
    if min(len(conditional_return), len(conditional_risk)) < 5:
        return None
    return {
        "phase": current_phase,
        "horizonYears": horizon_years,
        "return": {
            "count": int(len(conditional_return)),
            "mean": _json_value(conditional_return.mean()),
            "median": _json_value(conditional_return.median()),
            "positiveShare": _json_value((conditional_return > 0.0).mean()),
            "unconditionalMean": _json_value(unconditional_return.mean()),
            "differenceVsUnconditional": _json_value(
                conditional_return.mean() - unconditional_return.mean()
            ),
        },
        "risk": {
            "count": int(len(conditional_risk)),
            "mean": _json_value(conditional_risk.mean()),
            "median": _json_value(conditional_risk.median()),
            "unconditionalMean": _json_value(unconditional_risk.mean()),
            "differenceVsUnconditional": _json_value(
                conditional_risk.mean() - unconditional_risk.mean()
            ),
        },
    }


def _risk_classification_metrics(
    actual: pd.Series,
    probability: pd.Series,
) -> dict[str, object]:
    actual_array = actual.astype(int).to_numpy()
    probability_array = probability.astype(float).to_numpy()
    has_two_classes = len(np.unique(actual_array)) == 2
    return {
        "observations": len(actual_array),
        "events": int(actual_array.sum()),
        "eventRate": _json_value(actual_array.mean()),
        "auc": _json_value(
            roc_auc_score(actual_array, probability_array)
            if has_two_classes
            else None
        ),
        "averagePrecision": _json_value(
            average_precision_score(actual_array, probability_array)
            if has_two_classes
            else None
        ),
        "brier": _json_value(
            brier_score_loss(actual_array, probability_array)
        ),
    }


def _hierarchical_risk_prediction_frame(
    asset_universe: pd.DataFrame,
    jst: pd.DataFrame,
) -> pd.DataFrame:
    c2_panel = build_jst_panel(jst, "C2").sort_values(["iso", "year"])
    factor_pivot = c2_panel.pivot_table(
        index="year",
        columns="iso",
        values="factor",
        aggfunc="last",
    )
    country_count = factor_pivot.notna().sum(axis=1)
    global_activity = factor_pivot.median(axis=1).where(country_count >= 6)
    c2_panel["globalActivity"] = c2_panel["year"].map(global_activity)
    c2_panel["globalSlope"] = c2_panel["year"].map(global_activity.diff())
    c2_panel["countryDeviation"] = (
        c2_panel["factor"] - c2_panel["globalActivity"]
    )
    c2_panel["countryDeviationSlope"] = c2_panel.groupby("iso")[
        "countryDeviation"
    ].diff()
    c2_panel["mortgageCredit"] = c2_panel["family_mortgage_credit"]
    c2_panel["financingConditions"] = c2_panel[
        "family_financing_conditions"
    ]
    c2_panel["deviationFinancingInteraction"] = (
        c2_panel["countryDeviation"] * c2_panel["financingConditions"]
    )
    c2_panel["creditFinancingInteraction"] = (
        c2_panel["mortgageCredit"] * c2_panel["financingConditions"]
    )
    risk_panel = _country_risk_panel(jst)[
        ["iso", "year", "pressure", "confirmation"]
    ]
    c2_panel = c2_panel.merge(risk_panel, on=["iso", "year"], how="left")
    c2_panel["localActivity"] = c2_panel["factor"]
    c2_panel["localSlope"] = c2_panel.groupby("iso")["factor"].diff()
    c2_panel["laggedLocalActivity"] = c2_panel.groupby("iso")[
        "localActivity"
    ].shift(1)
    c2_panel["globalDownturn"] = (-c2_panel["globalSlope"]).clip(lower=0)
    c2_panel["localDownturn"] = (-c2_panel["localSlope"]).clip(lower=0)
    c2_panel["tightening"] = (-c2_panel["financingConditions"]).clip(
        lower=0
    )
    c2_panel["positivePressure"] = c2_panel["pressure"].clip(lower=0)
    c2_panel["boomReversal"] = (
        c2_panel["laggedLocalActivity"].clip(lower=0)
        * c2_panel["localDownturn"]
    )
    c2_panel["leverageReversal"] = (
        c2_panel["positivePressure"] * c2_panel["localDownturn"]
    )
    c2_panel["leverageTightening"] = (
        c2_panel["positivePressure"] * c2_panel["tightening"]
    )
    c2_panel["synchronizedDownturn"] = (
        c2_panel["globalDownturn"] * c2_panel["localDownturn"]
    )
    growth_rows: list[pd.DataFrame] = []
    for iso, group in jst.groupby("iso"):
        country = group.sort_values("year").set_index("year")
        real_gdp = pd.to_numeric(
            country["rgdpmad"], errors="coerce"
        ).where(lambda value: value > 0)
        growth_rows.append(
            pd.DataFrame(
                {
                    "iso": iso,
                    "year": country.index.astype(int),
                    "realGdpGrowth1Y": causal_robust_z(
                        np.log(real_gdp).diff()
                    ),
                }
            )
        )
    growth_panel = pd.concat(growth_rows, ignore_index=True)
    c2_panel = c2_panel.merge(growth_panel, on=["iso", "year"], how="left")
    c2_panel["laggedPositivePressure"] = c2_panel.groupby("iso")[
        "positivePressure"
    ].shift(1)
    c2_panel["scenarioHighLeverageEasing"] = (
        c2_panel["laggedPositivePressure"].clip(lower=0)
        * c2_panel["financingConditions"].clip(lower=0)
    )
    c2_panel["scenarioDownturnRecession"] = (
        (-c2_panel["family_housing_momentum"]).clip(lower=0)
        * (-c2_panel["realGdpGrowth1Y"]).clip(lower=0)
    )
    c2_panel["scenarioRecoveryCreditExpansion"] = (
        (-c2_panel["laggedLocalActivity"]).clip(lower=0)
        * c2_panel["family_housing_momentum"].clip(lower=0)
        * c2_panel["mortgageCredit"].clip(lower=0)
    )
    rate_rows: list[pd.DataFrame] = []
    for iso, group in jst.groupby("iso"):
        country = group.sort_values("year").copy()
        inflation = pd.to_numeric(country["cpi"], errors="coerce").pct_change()
        real_short_rate = pd.to_numeric(
            country["bill_rate"], errors="coerce"
        ) - inflation
        real_long_rate = pd.to_numeric(
            country["bond_rate"], errors="coerce"
        ) - inflation
        rate_rows.append(
            pd.DataFrame(
                {
                    "iso": iso,
                    "year": country["year"].astype(int),
                    "realShortRate": real_short_rate,
                    "realLongRate": real_long_rate,
                    "yieldCurve": real_long_rate - real_short_rate,
                    "shortRateChange": real_short_rate.diff(),
                    "longRateChange": real_long_rate.diff(),
                }
            )
        )
    rate_panel = pd.concat(rate_rows, ignore_index=True)
    c2_panel = c2_panel.merge(rate_panel, on=["iso", "year"], how="left")
    c2_panel["c2RealRateInteraction"] = (
        c2_panel["localActivity"] * c2_panel["realShortRate"]
    )
    c2_panel["pressureRealRateInteraction"] = (
        c2_panel["positivePressure"] * c2_panel["realShortRate"]
    )

    direct_assets = asset_universe.loc[
        (asset_universe["dataIdentity"] == "direct_historical_series")
        & asset_universe["category"].isin(C2_EVENT_ASSET_CATEGORIES)
    ]
    rows: list[pd.DataFrame] = []
    for _, asset in direct_assets.groupby("assetId"):
        asset = asset.sort_values("year").copy()
        returns = pd.to_numeric(asset["return"], errors="coerce")
        downside = -returns.clip(upper=0.0)
        asset["assetReturn"] = returns
        asset["assetMomentum3"] = returns.rolling(
            3,
            min_periods=2,
        ).mean()
        asset["assetChange1"] = returns.diff()
        asset["assetChange3"] = returns.diff(3) / 3.0
        asset["assetRisk3"] = np.sqrt(
            downside.pow(2).rolling(3, min_periods=2).mean()
        )
        asset["assetRisk5"] = np.sqrt(
            downside.pow(2).rolling(5, min_periods=3).mean()
        )
        for horizon_years in C2_EVENT_HORIZONS:
            horizon = asset.copy()
            horizon["horizonYears"] = horizon_years
            target_values = _annual_forward_path_values(
                asset,
                horizon_years=horizon_years,
            )
            for column, values in target_values.items():
                horizon[column] = horizon["year"].map(values)
            rows.append(horizon)
    asset_frame = pd.concat(rows, ignore_index=True)
    feature_columns = [
        "iso",
        "year",
        "globalActivity",
        "globalSlope",
        "countryDeviation",
        "countryDeviationSlope",
        "mortgageCredit",
        "financingConditions",
        "realGdpGrowth1Y",
        "realShortRate",
        "realLongRate",
        "yieldCurve",
        "shortRateChange",
        "longRateChange",
        "deviationFinancingInteraction",
        "creditFinancingInteraction",
        "c2RealRateInteraction",
        "pressureRealRateInteraction",
        *(
            scenario["column"]
            for scenario in C2_CONDITIONAL_PROPAGATION_SCENARIOS
        ),
        *C2_ASYMMETRIC_PRESSURE_COLUMNS,
    ]
    return asset_frame.merge(
        c2_panel[feature_columns],
        on=["iso", "year"],
        how="inner",
    )


def _historical_high_risk_labels(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    country_history = train.groupby("iso")["forwardRisk"].agg(
        ["count", lambda values: values.quantile(0.75)]
    )
    country_history.columns = ["count", "threshold"]
    country_thresholds = country_history.loc[
        country_history["count"] >= 20,
        "threshold",
    ]
    fallback_threshold = float(train["forwardRisk"].quantile(0.75))
    train_threshold = train["iso"].map(country_thresholds).fillna(
        fallback_threshold
    )
    test_threshold = test["iso"].map(country_thresholds).fillna(
        fallback_threshold
    )
    return (
        (
            (train["forwardRisk"] > 0.0)
            & (train["forwardRisk"] >= train_threshold)
        ).astype(int),
        (
            (test["forwardRisk"] > 0.0)
            & (test["forwardRisk"] >= test_threshold)
        ).astype(int),
    )


def _risk_classifier_predictions(
    train: pd.DataFrame,
    test: pd.DataFrame,
    columns: tuple[str, ...],
    *,
    regularization: float = 0.03,
) -> np.ndarray:
    model = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=regularization, max_iter=2_000),
    )
    model.fit(train[list(columns)], train["target"])
    return model.predict_proba(test[list(columns)])[:, 1]


def _hierarchical_risk_category_validation(
    frame: pd.DataFrame,
    *,
    category: str,
    horizon_years: int,
) -> tuple[dict[str, object], pd.DataFrame]:
    category_frame = frame.loc[
        (frame["category"] == category)
        & (frame["horizonYears"] == horizon_years)
        & frame["forwardRisk"].notna()
    ].copy()
    predictions: list[pd.DataFrame] = []
    for year in sorted(category_frame["year"].unique()):
        if year < 1950:
            continue
        train = category_frame.loc[
            category_frame["year"] <= year - horizon_years
        ].copy()
        test = category_frame.loc[category_frame["year"] == year].copy()
        if len(train) < 250 or test.empty:
            continue
        train["target"], test["target"] = _historical_high_risk_labels(
            train,
            test,
        )
        if train["target"].nunique() < 2:
            continue
        result = test[["year", "iso", "target"]].copy()
        result["category"] = category
        for architecture, columns in C2_RISK_ARCHITECTURES.items():
            result[architecture] = _risk_classifier_predictions(
                train,
                test,
                columns,
            )
        predictions.append(result)
    prediction_frame = pd.concat(predictions, ignore_index=True)
    metrics = {
        architecture: _risk_classification_metrics(
            prediction_frame["target"],
            prediction_frame[architecture],
        )
        for architecture in C2_RISK_ARCHITECTURES
    }
    persistence = metrics["asset_persistence"]
    hierarchy = metrics["country_hierarchy"]
    auc_delta = (
        float(hierarchy["auc"]) - float(persistence["auc"])
        if hierarchy["auc"] is not None and persistence["auc"] is not None
        else None
    )
    brier_improvement = float(persistence["brier"]) - float(
        hierarchy["brier"]
    )
    return (
        {
            "category": category,
            "observations": len(prediction_frame),
            "architectures": metrics,
            "incrementalVsPersistence": {
                "aucDelta": _json_value(auc_delta),
                "brierImprovement": _json_value(brier_improvement),
                "rankingImproved": auc_delta is not None and auc_delta > 0.0,
                "calibrationImproved": brier_improvement > 0.0,
            },
        },
        prediction_frame,
    )


def _risk_model_comparison(
    frame: pd.DataFrame,
    *,
    baseline_column: str,
    candidate_column: str,
) -> dict[str, object]:
    baseline = _risk_classification_metrics(
        frame["target"],
        frame[baseline_column],
    )
    candidate = _risk_classification_metrics(
        frame["target"],
        frame[candidate_column],
    )
    baseline_auc = baseline["auc"]
    candidate_auc = candidate["auc"]
    baseline_average_precision = baseline["averagePrecision"]
    candidate_average_precision = candidate["averagePrecision"]
    return {
        "baseline": baseline,
        "candidate": candidate,
        "aucDelta": _json_value(
            float(candidate_auc) - float(baseline_auc)
            if candidate_auc is not None and baseline_auc is not None
            else None
        ),
        "brierImprovement": _json_value(
            float(baseline["brier"]) - float(candidate["brier"])
        ),
        "averagePrecisionDelta": _json_value(
            float(candidate_average_precision)
            - float(baseline_average_precision)
            if candidate_average_precision is not None
            and baseline_average_precision is not None
            else None
        ),
    }


def _asset_target_labels(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    value_column: str,
    label_mode: str,
) -> tuple[pd.Series, pd.Series]:
    if label_mode == "positive":
        return (
            (train[value_column] > 0.0).astype(int),
            (test[value_column] > 0.0).astype(int),
        )
    country_history = train.groupby("iso")[value_column].agg(
        ["count", lambda values: values.quantile(0.75)]
    )
    country_history.columns = ["count", "threshold"]
    country_thresholds = country_history.loc[
        country_history["count"] >= 20,
        "threshold",
    ]
    fallback_threshold = float(train[value_column].quantile(0.75))
    train_threshold = train["iso"].map(country_thresholds).fillna(
        fallback_threshold
    )
    test_threshold = test["iso"].map(country_thresholds).fillna(
        fallback_threshold
    )
    return (
        (train[value_column] >= train_threshold).astype(int),
        (test[value_column] >= test_threshold).astype(int),
    )


def _asset_class_target_validation(
    frame: pd.DataFrame,
    *,
    category: str,
    horizon_years: int,
    target_spec: dict[str, str],
) -> dict[str, object]:
    value_column = target_spec["valueColumn"]
    source = frame.loc[
        (frame["category"] == category)
        & (frame["horizonYears"] == horizon_years)
        & frame[value_column].notna()
    ].copy()
    baseline_columns = C2_ASSET_CLASS_BASELINES[category]
    candidate_columns = tuple(
        dict.fromkeys(
            (*baseline_columns, *C2_ASSET_CLASS_INCREMENTS[category])
        )
    )
    recursive_rows: list[pd.DataFrame] = []
    for year in sorted(source["year"].unique()):
        if year < 1950:
            continue
        train = source.loc[source["year"] <= year - horizon_years].copy()
        test = source.loc[source["year"] == year].copy()
        if len(train) < 250 or test.empty:
            continue
        train["target"], test["target"] = _asset_target_labels(
            train,
            test,
            value_column=value_column,
            label_mode=target_spec["labelMode"],
        )
        if train["target"].nunique() < 2:
            continue
        result = test[
            ["year", "iso", "target", "realShortRate", "shortRateChange"]
        ].copy()
        for regularization in C2_RISK_PARAMETER_GRID:
            suffix = f"{regularization:.2f}"
            result[f"baseline_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                baseline_columns,
                regularization=regularization,
            )
            result[f"candidate_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                candidate_columns,
                regularization=regularization,
            )
        recursive_rows.append(result)
    recursive = pd.concat(recursive_rows, ignore_index=True)
    parameter_plateau = []
    for regularization in C2_RISK_PARAMETER_GRID:
        suffix = f"{regularization:.2f}"
        parameter_plateau.append(
            {
                "regularization": regularization,
                **_risk_model_comparison(
                    recursive,
                    baseline_column=f"baseline_{suffix}",
                    candidate_column=f"candidate_{suffix}",
                ),
            }
        )
    selected_suffix = "0.03"
    recursive_comparison = _risk_model_comparison(
        recursive,
        baseline_column=f"baseline_{selected_suffix}",
        candidate_column=f"candidate_{selected_suffix}",
    )
    subperiods = []
    for start_year, end_year in ((1950, 1984), (1985, 2020)):
        period = recursive.loc[recursive["year"].between(start_year, end_year)]
        subperiods.append(
            {
                "startYear": start_year,
                "endYear": end_year,
                **_risk_model_comparison(
                    period,
                    baseline_column=f"baseline_{selected_suffix}",
                    candidate_column=f"candidate_{selected_suffix}",
                ),
            }
        )

    country_rows: list[pd.DataFrame] = []
    for iso in sorted(source["iso"].unique()):
        train = source.loc[
            (source["iso"] != iso)
            & (source["year"] <= 1999 - horizon_years)
        ].copy()
        test = source.loc[
            (source["iso"] == iso) & (source["year"] >= 2000)
        ].copy()
        held_history = source.loc[
            (source["iso"] == iso)
            & (source["year"] <= 1999 - horizon_years),
            value_column,
        ].dropna()
        if len(train) < 700 or len(test) < 10:
            continue
        train["target"], _ = _asset_target_labels(
            train,
            train,
            value_column=value_column,
            label_mode=target_spec["labelMode"],
        )
        if target_spec["labelMode"] == "positive":
            test["target"] = (test[value_column] > 0.0).astype(int)
        else:
            if len(held_history) < 20:
                continue
            held_threshold = float(held_history.quantile(0.75))
            test["target"] = (
                test[value_column] >= held_threshold
            ).astype(int)
        if train["target"].nunique() < 2:
            continue
        result = test[["year", "iso", "target"]].copy()
        result["baseline"] = _risk_classifier_predictions(
            train,
            test,
            baseline_columns,
        )
        result["candidate"] = _risk_classifier_predictions(
            train,
            test,
            candidate_columns,
        )
        country_rows.append(result)
    country_holdout = pd.concat(country_rows, ignore_index=True)
    country_comparison = _risk_model_comparison(
        country_holdout,
        baseline_column="baseline",
        candidate_column="candidate",
    )
    country_details = []
    for iso, country in country_holdout.groupby("iso"):
        comparison = _risk_model_comparison(
            country,
            baseline_column="baseline",
            candidate_column="candidate",
        )
        country_details.append(
            {
                "iso": str(iso),
                "observations": len(country),
                "events": int(country["target"].sum()),
                **comparison,
            }
        )
    improved_country_share = float(
        np.mean(
            [
                row["aucDelta"] is not None
                and float(row["aucDelta"]) > 0.0
                and float(row["brierImprovement"]) > 0.0
                for row in country_details
            ]
        )
    )
    rate_regimes: list[dict[str, object]] = []
    if category == "跨国国债":
        regime_masks = {
            "negative_real_rate": recursive["realShortRate"] < 0.0,
            "nonnegative_real_rate": recursive["realShortRate"] >= 0.0,
            "falling_short_rate": recursive["shortRateChange"] < 0.0,
            "rising_short_rate": recursive["shortRateChange"] >= 0.0,
        }
        for regime_id, mask in regime_masks.items():
            regime = recursive.loc[mask].dropna(
                subset=["target", f"baseline_{selected_suffix}", f"candidate_{selected_suffix}"]
            )
            if len(regime) < 100 or regime["target"].nunique() < 2:
                continue
            rate_regimes.append(
                {
                    "regimeId": regime_id,
                    **_risk_model_comparison(
                        regime,
                        baseline_column=f"baseline_{selected_suffix}",
                        candidate_column=f"candidate_{selected_suffix}",
                    ),
                }
            )
    rate_regime_stable = category != "跨国国债" or (
        len(rate_regimes) == 4
        and all(
            row["aucDelta"] is not None
            and float(row["candidate"]["auc"]) >= 0.55
            and float(row["aucDelta"]) > 0.0
            and float(row["brierImprovement"]) > 0.0
            for row in rate_regimes
        )
    )
    parameter_stable = all(
        row["aucDelta"] is not None
        and float(row["candidate"]["auc"]) >= 0.58
        and float(row["aucDelta"]) > 0.0
        and float(row["brierImprovement"]) > 0.0
        for row in parameter_plateau
    )
    subperiod_stable = all(
        row["aucDelta"] is not None
        and float(row["candidate"]["auc"]) >= 0.58
        and float(row["aucDelta"]) > 0.0
        and float(row["brierImprovement"]) > 0.0
        for row in subperiods
    )
    passed = (
        len(recursive) >= 1_000
        and recursive_comparison["aucDelta"] is not None
        and float(recursive_comparison["candidate"]["auc"]) >= 0.60
        and float(recursive_comparison["aucDelta"]) >= 0.02
        and float(recursive_comparison["brierImprovement"]) >= 0.002
        and parameter_stable
        and subperiod_stable
        and rate_regime_stable
        and country_comparison["aucDelta"] is not None
        and float(country_comparison["candidate"]["auc"]) >= 0.60
        and float(country_comparison["aucDelta"]) >= 0.02
        and float(country_comparison["brierImprovement"]) >= 0.002
        and improved_country_share >= 0.60
    )
    return {
        "targetId": target_spec["targetId"],
        "label": target_spec["label"],
        "definition": target_spec["definition"],
        "horizonYears": horizon_years,
        "status": "passed_historical_channel" if passed else "failed",
        "recursiveValidation": recursive_comparison,
        "parameterPlateau": parameter_plateau,
        "subperiods": subperiods,
        "rateRegimes": rate_regimes,
        "rateRegimeStable": rate_regime_stable,
        "leaveCountryOut2000Plus": {
            **country_comparison,
            "countryCount": len(country_details),
            "improvedCountryShare": _json_value(improved_country_share),
            "countries": country_details,
        },
        "features": {
            "baseline": list(baseline_columns),
            "c2Increment": list(C2_ASSET_CLASS_INCREMENTS[category]),
        },
        "gate": {
            "minimumObservations": 1_000,
            "minimumCandidateAuc": 0.60,
            "minimumAucDelta": 0.02,
            "minimumBrierImprovement": 0.002,
            "parameterPlateauRequired": True,
            "minimumSubperiodAuc": 0.58,
            "bondRateRegimesRequired": category == "跨国国债",
            "minimumCountryHoldoutAuc": 0.60,
            "minimumCountryHoldoutAucDelta": 0.02,
            "minimumImprovedCountryShare": 0.60,
        },
    }


def _asset_class_specific_validation(
    frame: pd.DataFrame,
) -> dict[str, object]:
    classes = []
    passed_targets = 0
    total_targets = 0
    for category, target_specs in C2_ASSET_CLASS_TARGETS.items():
        targets = []
        for horizon_years in C2_EVENT_HORIZONS:
            for target_spec in target_specs:
                validation = _asset_class_target_validation(
                    frame,
                    category=category,
                    horizon_years=horizon_years,
                    target_spec=target_spec,
                )
                targets.append(validation)
                passed_targets += int(
                    validation["status"] == "passed_historical_channel"
                )
                total_targets += 1
        class_passed = sum(
            target["status"] == "passed_historical_channel"
            for target in targets
        )
        classes.append(
            {
                "category": category,
                "status": (
                    "passed_limited" if class_passed else "failed"
                ),
                "passedTargets": class_passed,
                "targetCount": len(targets),
                "targets": targets,
            }
        )
    return {
        "status": "passed_limited" if passed_targets else "failed",
        "assetForecastStatus": "blocked",
        "passedTargets": passed_targets,
        "targetCount": total_targets,
        "classes": classes,
        "method": "股票、国债、短票分别定义目标和资产自身基线，再在完全相同的递归年份样本外框架中检验C2增量；同时要求参数平台、前后时期和国家留一通过。",
        "interpretation": "股票检验收益方向与最大回撤；国债检验实际收益方向与下行损失并加入实际利率环境；短票检验实际短端收益方向与利率冲击，不再把普通波动当作目标。",
        "caveat": "历史通道即使通过，也只说明C2提供稳定增量；在当前数据桥接和概率校准完成前，仍不输出当前资产概率或配置权重。",
    }


def _conditional_propagation_target_validation(
    frame: pd.DataFrame,
    *,
    category: str,
    horizon_years: int,
    target_spec: dict[str, str],
    scenario: dict[str, str],
) -> dict[str, object]:
    value_column = target_spec["valueColumn"]
    scenario_column = scenario["column"]
    source = frame.loc[
        (frame["category"] == category)
        & (frame["horizonYears"] == horizon_years)
        & frame[value_column].notna()
        & frame[scenario_column].notna()
    ].copy()
    baseline_columns = C2_ASSET_CLASS_BASELINES[category]
    candidate_columns = (*baseline_columns, scenario_column)
    recursive_rows: list[pd.DataFrame] = []
    for year in sorted(source["year"].unique()):
        if year < 1950:
            continue
        train = source.loc[source["year"] <= year - horizon_years].copy()
        test = source.loc[source["year"] == year].copy()
        if len(train) < 250 or test.empty:
            continue
        train["target"], test["target"] = _asset_target_labels(
            train,
            test,
            value_column=value_column,
            label_mode=target_spec["labelMode"],
        )
        if train["target"].nunique() < 2:
            continue
        result = test[["year", "iso", "target", scenario_column]].copy()
        result = result.rename(columns={scenario_column: "scenarioValue"})
        for regularization in C2_RISK_PARAMETER_GRID:
            suffix = f"{regularization:.2f}"
            result[f"baseline_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                baseline_columns,
                regularization=regularization,
            )
            result[f"candidate_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                candidate_columns,
                regularization=regularization,
            )
        recursive_rows.append(result)
    recursive = pd.concat(recursive_rows, ignore_index=True)
    selected_suffix = "0.03"
    recursive_comparison = _risk_model_comparison(
        recursive,
        baseline_column=f"baseline_{selected_suffix}",
        candidate_column=f"candidate_{selected_suffix}",
    )
    active_recursive = recursive.loc[recursive["scenarioValue"] > 0.0]
    active_comparison = _risk_model_comparison(
        active_recursive,
        baseline_column=f"baseline_{selected_suffix}",
        candidate_column=f"candidate_{selected_suffix}",
    )
    parameter_plateau = []
    for regularization in C2_RISK_PARAMETER_GRID:
        suffix = f"{regularization:.2f}"
        parameter_plateau.append(
            {
                "regularization": regularization,
                **_risk_model_comparison(
                    recursive,
                    baseline_column=f"baseline_{suffix}",
                    candidate_column=f"candidate_{suffix}",
                ),
            }
        )
    subperiods = []
    for start_year, end_year in ((1950, 1984), (1985, 2020)):
        period = recursive.loc[recursive["year"].between(start_year, end_year)]
        active_period = period.loc[period["scenarioValue"] > 0.0]
        subperiods.append(
            {
                "startYear": start_year,
                "endYear": end_year,
                "activeObservations": len(active_period),
                "activeCountries": int(active_period["iso"].nunique()),
                **_risk_model_comparison(
                    period,
                    baseline_column=f"baseline_{selected_suffix}",
                    candidate_column=f"candidate_{selected_suffix}",
                ),
                "activeComparison": _risk_model_comparison(
                    active_period,
                    baseline_column=f"baseline_{selected_suffix}",
                    candidate_column=f"candidate_{selected_suffix}",
                ),
            }
        )

    country_rows: list[pd.DataFrame] = []
    for iso in sorted(source["iso"].unique()):
        train = source.loc[
            (source["iso"] != iso)
            & (source["year"] <= 1999 - horizon_years)
        ].copy()
        test = source.loc[
            (source["iso"] == iso) & (source["year"] >= 2000)
        ].copy()
        held_history = source.loc[
            (source["iso"] == iso)
            & (source["year"] <= 1999 - horizon_years),
            value_column,
        ].dropna()
        if len(train) < 700 or len(test) < 10:
            continue
        train["target"], _ = _asset_target_labels(
            train,
            train,
            value_column=value_column,
            label_mode=target_spec["labelMode"],
        )
        if target_spec["labelMode"] == "positive":
            test["target"] = (test[value_column] > 0.0).astype(int)
        else:
            if len(held_history) < 20:
                continue
            held_threshold = float(held_history.quantile(0.75))
            test["target"] = (
                test[value_column] >= held_threshold
            ).astype(int)
        if train["target"].nunique() < 2:
            continue
        result = test[["year", "iso", "target", scenario_column]].copy()
        result = result.rename(columns={scenario_column: "scenarioValue"})
        result["baseline"] = _risk_classifier_predictions(
            train,
            test,
            baseline_columns,
        )
        result["candidate"] = _risk_classifier_predictions(
            train,
            test,
            candidate_columns,
        )
        country_rows.append(result)
    country_holdout = pd.concat(country_rows, ignore_index=True)
    country_comparison = _risk_model_comparison(
        country_holdout,
        baseline_column="baseline",
        candidate_column="candidate",
    )
    active_country_holdout = country_holdout.loc[
        country_holdout["scenarioValue"] > 0.0
    ]
    country_details = []
    for iso, country in country_holdout.groupby("iso"):
        comparison = _risk_model_comparison(
            country,
            baseline_column="baseline",
            candidate_column="candidate",
        )
        country_details.append(
            {
                "iso": str(iso),
                "observations": len(country),
                "activeObservations": int((country["scenarioValue"] > 0.0).sum()),
                "events": int(country["target"].sum()),
                **comparison,
            }
        )
    improved_country_share = float(
        np.mean(
            [
                row["aucDelta"] is not None
                and float(row["aucDelta"]) > 0.0
                and float(row["brierImprovement"]) > 0.0
                for row in country_details
            ]
        )
    )
    parameter_stable = all(
        row["aucDelta"] is not None
        and float(row["candidate"]["auc"]) >= 0.58
        and float(row["aucDelta"]) > 0.0
        and float(row["brierImprovement"]) > 0.0
        for row in parameter_plateau
    )
    subperiod_stable = all(
        row["aucDelta"] is not None
        and float(row["candidate"]["auc"]) >= 0.58
        and float(row["aucDelta"]) > 0.0
        and float(row["brierImprovement"]) > 0.0
        and row["activeComparison"]["aucDelta"] is not None
        and float(row["activeComparison"]["aucDelta"]) > 0.0
        and float(row["activeComparison"]["brierImprovement"]) > 0.0
        and int(row["activeObservations"]) >= 15
        and int(row["activeCountries"]) >= 8
        for row in subperiods
    )
    coverage_sufficient = (
        len(active_recursive) >= 40
        and int(active_recursive["iso"].nunique()) >= 10
        and len(active_country_holdout) >= 20
        and int(active_country_holdout["iso"].nunique()) >= 8
    )
    passed = (
        len(recursive) >= 1_000
        and coverage_sufficient
        and recursive_comparison["aucDelta"] is not None
        and float(recursive_comparison["candidate"]["auc"]) >= 0.60
        and float(recursive_comparison["aucDelta"]) >= 0.02
        and float(recursive_comparison["brierImprovement"]) >= 0.002
        and active_comparison["aucDelta"] is not None
        and float(active_comparison["aucDelta"]) > 0.0
        and float(active_comparison["brierImprovement"]) > 0.0
        and parameter_stable
        and subperiod_stable
        and country_comparison["aucDelta"] is not None
        and float(country_comparison["candidate"]["auc"]) >= 0.60
        and float(country_comparison["aucDelta"]) >= 0.02
        and float(country_comparison["brierImprovement"]) >= 0.002
        and improved_country_share >= 0.60
    )
    return {
        "scenarioId": scenario["scenarioId"],
        "scenarioLabel": scenario["label"],
        "category": category,
        "targetId": target_spec["targetId"],
        "targetLabel": target_spec["label"],
        "horizonYears": horizon_years,
        "status": (
            "passed_historical_channel"
            if passed
            else "insufficient_scenario_coverage"
            if not coverage_sufficient
            else "failed"
        ),
        "recursiveValidation": recursive_comparison,
        "activeRecursiveValidation": {
            **active_comparison,
            "activeObservations": len(active_recursive),
            "activeCountries": int(active_recursive["iso"].nunique()),
        },
        "parameterPlateau": parameter_plateau,
        "subperiods": subperiods,
        "leaveCountryOut2000Plus": {
            **country_comparison,
            "countryCount": len(country_details),
            "activeObservations": len(active_country_holdout),
            "activeCountries": int(active_country_holdout["iso"].nunique()),
            "improvedCountryShare": _json_value(improved_country_share),
            "countries": country_details,
        },
        "coverageSufficient": coverage_sufficient,
        "features": {
            "baseline": list(baseline_columns),
            "conditionalSignal": scenario_column,
        },
        "gate": {
            "minimumObservations": 1_000,
            "minimumActiveObservations": 40,
            "minimumActiveCountries": 10,
            "minimumHoldoutActiveObservations": 20,
            "minimumHoldoutActiveCountries": 8,
            "minimumCandidateAuc": 0.60,
            "minimumAucDelta": 0.02,
            "minimumBrierImprovement": 0.002,
            "activeAucMustImprove": True,
            "activeBrierMustImprove": True,
            "parameterPlateauRequired": True,
            "subperiodStabilityRequired": True,
            "minimumCountryHoldoutAuc": 0.60,
            "minimumCountryHoldoutAucDelta": 0.02,
            "minimumImprovedCountryShare": 0.60,
        },
    }


def _conditional_propagation_validation(
    frame: pd.DataFrame,
) -> dict[str, object]:
    scenario_rows = []
    total_channels = 0
    passed_channels = 0
    insufficient_channels = 0
    for scenario in C2_CONDITIONAL_PROPAGATION_SCENARIOS:
        channels = []
        for category, target_specs in C2_ASSET_CLASS_TARGETS.items():
            for horizon_years in C2_EVENT_HORIZONS:
                for target_spec in target_specs:
                    channel = _conditional_propagation_target_validation(
                        frame,
                        category=category,
                        horizon_years=horizon_years,
                        target_spec=target_spec,
                        scenario=scenario,
                    )
                    channels.append(channel)
                    total_channels += 1
                    passed_channels += int(
                        channel["status"] == "passed_historical_channel"
                    )
                    insufficient_channels += int(
                        channel["status"] == "insufficient_scenario_coverage"
                    )
        scenario_passed = sum(
            channel["status"] == "passed_historical_channel"
            for channel in channels
        )
        positive_full_sample = sum(
            channel["recursiveValidation"]["aucDelta"] is not None
            and float(channel["recursiveValidation"]["aucDelta"]) > 0.0
            and float(channel["recursiveValidation"]["brierImprovement"]) > 0.0
            for channel in channels
        )
        scenario_rows.append(
            {
                "scenarioId": scenario["scenarioId"],
                "label": scenario["label"],
                "definition": scenario["definition"],
                "status": (
                    "passed_limited" if scenario_passed else "failed"
                ),
                "passedChannels": scenario_passed,
                "channelCount": len(channels),
                "positiveFullSampleChannels": positive_full_sample,
                "medianAucDelta": _json_value(
                    np.median(
                        [
                            float(channel["recursiveValidation"]["aucDelta"])
                            for channel in channels
                            if channel["recursiveValidation"]["aucDelta"]
                            is not None
                        ]
                    )
                ),
                "channels": channels,
            }
        )
    close_standalone_path = passed_channels == 0
    return {
        "status": "passed_limited" if passed_channels else "failed",
        "assetForecastStatus": "blocked",
        "decision": (
            "retain_limited_conditional_channels"
            if passed_channels
            else "close_standalone_c2_asset_prediction"
        ),
        "passedChannels": passed_channels,
        "channelCount": total_channels,
        "insufficientCoverageChannels": insufficient_channels,
        "scenarios": scenario_rows,
        "method": "固定三种经济传播场景，每次只在资产自身基线上增加一个预注册条件信号；对股票、国债和短票的12个资产—期限目标分别执行递归年份样本外、参数平台、前后时期和国家留一验证。",
        "interpretation": "该检验回答C2是否只在明确传播环境下提供资产增量，不搜索任意行业映射，也不允许用局部时期结果解除阻断。",
        "conclusion": (
            "存在通过完整门槛的有限条件通道，仍需当前数据桥接后才能研究实时概率。"
            if not close_standalone_path
            else "三种预注册传播场景均未建立稳定资产增量，停止继续扩充C2单周期资产模型；C2只保留为宏观状态和七周期联合模型中的条件交互。"
        ),
        "caveat": "年度宏观历史为因果重建而非真实发布vintage；未通过项不能生成当前资产概率、收益方向或配置权重。",
    }


def _macro_bond_risk_validation(
    source: pd.DataFrame,
) -> dict[str, object]:
    recursive_rows: list[pd.DataFrame] = []
    for year in sorted(source["year"].unique()):
        if year < 1950:
            continue
        train = source.loc[source["year"] <= year - 3].copy()
        test = source.loc[source["year"] == year].copy()
        if len(train) < 250 or test.empty:
            continue
        train["target"], test["target"] = _historical_high_risk_labels(
            train,
            test,
        )
        result = test[["year", "iso", "target"]].copy()
        for regularization in C2_RISK_PARAMETER_GRID:
            suffix = f"{regularization:.2f}"
            result[f"baseline_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                C2_ASSET_PERSISTENCE_COLUMNS,
                regularization=regularization,
            )
            result[f"candidate_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                C2_MACRO_PRESSURE_COLUMNS,
                regularization=regularization,
            )
        recursive_rows.append(result)
    recursive = pd.concat(recursive_rows, ignore_index=True)
    parameter_plateau = []
    for regularization in C2_RISK_PARAMETER_GRID:
        suffix = f"{regularization:.2f}"
        parameter_plateau.append(
            {
                "regularization": regularization,
                **_risk_model_comparison(
                    recursive,
                    baseline_column=f"baseline_{suffix}",
                    candidate_column=f"candidate_{suffix}",
                ),
            }
        )
    selected_suffix = "0.03"
    recursive_comparison = _risk_model_comparison(
        recursive,
        baseline_column=f"baseline_{selected_suffix}",
        candidate_column=f"candidate_{selected_suffix}",
    )
    subperiods = []
    for start_year, end_year in ((1950, 1984), (1985, 2020)):
        period = recursive.loc[recursive["year"].between(start_year, end_year)]
        subperiods.append(
            {
                "startYear": start_year,
                "endYear": end_year,
                **_risk_model_comparison(
                    period,
                    baseline_column=f"baseline_{selected_suffix}",
                    candidate_column=f"candidate_{selected_suffix}",
                ),
            }
        )

    country_rows: list[pd.DataFrame] = []
    for iso in sorted(source["iso"].unique()):
        train = source.loc[
            (source["iso"] != iso) & (source["year"] <= 1999)
        ].copy()
        test = source.loc[
            (source["iso"] == iso) & (source["year"] >= 2000)
        ].copy()
        held_history = source.loc[
            (source["iso"] == iso) & (source["year"] <= 1996),
            "forwardRisk",
        ].dropna()
        if len(train) < 700 or len(test) < 10 or len(held_history) < 20:
            continue
        train["target"], _ = _historical_high_risk_labels(train, train)
        held_threshold = float(held_history.quantile(0.75))
        test["target"] = (
            (test["forwardRisk"] > 0.0)
            & (test["forwardRisk"] >= held_threshold)
        ).astype(int)
        if train["target"].nunique() < 2 or test["target"].nunique() < 2:
            continue
        result = test[["year", "iso", "target"]].copy()
        result["baseline"] = _risk_classifier_predictions(
            train,
            test,
            C2_ASSET_PERSISTENCE_COLUMNS,
        )
        result["candidate"] = _risk_classifier_predictions(
            train,
            test,
            C2_MACRO_PRESSURE_COLUMNS,
        )
        country_rows.append(result)
    country_holdout = pd.concat(country_rows, ignore_index=True)
    country_comparison = _risk_model_comparison(
        country_holdout,
        baseline_column="baseline",
        candidate_column="candidate",
    )
    country_details = []
    for iso, country in country_holdout.groupby("iso"):
        comparison = _risk_model_comparison(
            country,
            baseline_column="baseline",
            candidate_column="candidate",
        )
        country_details.append(
            {
                "iso": str(iso),
                "observations": len(country),
                "events": int(country["target"].sum()),
                **comparison,
            }
        )
    improved_country_share = float(
        np.mean([float(row["aucDelta"]) > 0.0 for row in country_details])
    )
    parameter_stable = all(
        float(row["candidate"]["auc"]) >= 0.61
        and float(row["brierImprovement"]) > 0.0
        for row in parameter_plateau
    )
    subperiod_stable = all(
        float(row["candidate"]["auc"]) >= 0.60
        and float(row["brierImprovement"]) > 0.0
        for row in subperiods
    )
    passed = (
        len(recursive) >= 1_000
        and float(recursive_comparison["candidate"]["auc"]) >= 0.61
        and float(recursive_comparison["aucDelta"]) >= 0.02
        and float(recursive_comparison["brierImprovement"]) >= 0.005
        and parameter_stable
        and subperiod_stable
        and float(country_comparison["candidate"]["auc"]) >= 0.64
        and float(country_comparison["aucDelta"]) >= 0.08
        and float(country_comparison["brierImprovement"]) >= 0.005
        and improved_country_share >= 0.80
    )
    return {
        "status": "passed_historical_stress" if passed else "failed",
        "architecture": "结构高压 + 高位转弱 + 全球与本国同步下行；不使用当前国债收益或融资条件",
        "features": list(C2_MACRO_PRESSURE_COLUMNS),
        "recursiveValidation": recursive_comparison,
        "parameterPlateau": parameter_plateau,
        "subperiods": subperiods,
        "leaveCountryOut2000Plus": {
            **country_comparison,
            "countryCount": len(country_details),
            "improvedCountryShare": _json_value(improved_country_share),
            "countries": country_details,
        },
        "gate": {
            "minimumCandidateAuc": 0.61,
            "minimumAucDelta": 0.02,
            "minimumBrierImprovement": 0.005,
            "minimumCountryHoldoutAuc": 0.64,
            "minimumCountryHoldoutAucDelta": 0.08,
            "minimumImprovedCountryShare": 0.80,
        },
        "interpretation": "即使完全移除资产自身收益与融资条件，地产—信用结构压力仍对未来3年国债高风险状态提供历史增量信息。",
    }


def _align_country_proxy(
    historical: pd.DataFrame,
    proxy: pd.DataFrame,
    *,
    historical_column: str,
    proxy_column: str,
    output_column: str,
    alignment_end_year: int = 1999,
    minimum_country_overlap: int = 12,
) -> pd.DataFrame:
    overlap = historical[["iso", "year", historical_column]].merge(
        proxy[["iso", "year", proxy_column]],
        on=["iso", "year"],
        how="inner",
    )
    overlap = overlap.loc[overlap["year"] <= alignment_end_year].dropna()
    global_proxy_mean = float(overlap[proxy_column].mean())
    global_proxy_std = float(overlap[proxy_column].std(ddof=0))
    global_historical_mean = float(overlap[historical_column].mean())
    global_historical_std = float(overlap[historical_column].std(ddof=0))
    aligned = []
    for iso, country in proxy.groupby("iso"):
        country = country.sort_values("year").copy()
        calibration = overlap.loc[overlap["iso"] == iso]
        use_country = (
            len(calibration) >= minimum_country_overlap
            and float(calibration[proxy_column].std(ddof=0)) > 1e-8
            and float(calibration[historical_column].std(ddof=0)) > 1e-8
        )
        if use_country:
            proxy_mean = float(calibration[proxy_column].mean())
            proxy_std = float(calibration[proxy_column].std(ddof=0))
            historical_mean = float(calibration[historical_column].mean())
            historical_std = float(calibration[historical_column].std(ddof=0))
        else:
            proxy_mean = global_proxy_mean
            proxy_std = global_proxy_std
            historical_mean = global_historical_mean
            historical_std = global_historical_std
        country[output_column] = (
            (country[proxy_column] - proxy_mean)
            / proxy_std
            * historical_std
            + historical_mean
        )
        country[f"{output_column}Alignment"] = (
            "country_overlap" if use_country else "pooled_overlap"
        )
        aligned.append(country)
    return pd.concat(aligned, ignore_index=True)


def _proxy_overlap_validation(
    historical: pd.DataFrame,
    proxy: pd.DataFrame,
    *,
    historical_column: str,
    proxy_column: str,
    start_year: int,
    end_year: int,
    minimum_country_observations: int = 8,
) -> dict[str, object]:
    historical_value = "_historical_value"
    proxy_value = "_proxy_value"
    frame = historical[["iso", "year", historical_column]].rename(
        columns={historical_column: historical_value}
    ).merge(
        proxy[["iso", "year", proxy_column]].rename(
            columns={proxy_column: proxy_value}
        ),
        on=["iso", "year"],
        how="inner",
    )
    frame = frame.loc[frame["year"].between(start_year, end_year)].dropna()
    countries = []
    for iso, country in frame.groupby("iso"):
        if len(country) < minimum_country_observations:
            continue
        countries.append(
            {
                "iso": str(iso),
                "observations": len(country),
                "correlation": _json_value(
                    country[historical_value].corr(country[proxy_value])
                ),
                "directionAgreement": _json_value(
                    np.mean(
                        np.sign(country[historical_value])
                        == np.sign(country[proxy_value])
                    )
                ),
            }
        )
    correlations = [
        float(row["correlation"])
        for row in countries
        if row["correlation"] is not None
    ]
    direction_agreements = [
        float(row["directionAgreement"]) for row in countries
    ]
    return {
        "observations": len(frame),
        "countryCount": int(frame["iso"].nunique()),
        "startYear": int(frame["year"].min()),
        "endYear": int(frame["year"].max()),
        "correlation": _json_value(
            frame[historical_value].corr(frame[proxy_value])
        ),
        "directionAgreement": _json_value(
            np.mean(
                np.sign(frame[historical_value])
                == np.sign(frame[proxy_value])
            )
        ),
        "countryMedianCorrelation": _json_value(np.median(correlations)),
        "countryMedianDirectionAgreement": _json_value(
            np.median(direction_agreements)
        ),
        "countries": countries,
    }


def _modern_macro_pressure_features(
    historical_panel: pd.DataFrame,
    bridge_panel: pd.DataFrame,
    historical_pressure: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    aligned_activity = _align_bridge_factor(
        historical_panel,
        bridge_panel,
        alignment_end_year=1999,
    )
    aligned_pressure = _align_country_proxy(
        historical_pressure,
        bridge_panel,
        historical_column="pressure",
        proxy_column="structural_pressure",
        output_column="pressure",
    )
    panel = aligned_activity.merge(
        aligned_pressure[
            [
                "iso",
                "year",
                "pressure",
                "pressureAlignment",
            ]
        ],
        on=["iso", "year"],
        how="left",
    ).sort_values(["iso", "year"])
    factor_pivot = panel.pivot_table(
        index="year",
        columns="iso",
        values="factor",
        aggfunc="last",
    )
    country_count = factor_pivot.notna().sum(axis=1)
    global_activity = factor_pivot.median(axis=1).where(country_count >= 6)
    panel["globalActivity"] = panel["year"].map(global_activity)
    panel["globalSlope"] = panel["year"].map(global_activity.diff())
    panel["localActivity"] = panel["factor"]
    panel["localSlope"] = panel.groupby("iso")["factor"].diff()
    panel["laggedLocalActivity"] = panel.groupby("iso")[
        "localActivity"
    ].shift(1)
    panel["globalDownturn"] = (-panel["globalSlope"]).clip(lower=0)
    panel["localDownturn"] = (-panel["localSlope"]).clip(lower=0)
    panel["positivePressure"] = panel["pressure"].clip(lower=0)
    panel["boomReversal"] = (
        panel["laggedLocalActivity"].clip(lower=0)
        * panel["localDownturn"]
    )
    panel["leverageReversal"] = (
        panel["positivePressure"] * panel["localDownturn"]
    )
    panel["synchronizedDownturn"] = (
        panel["globalDownturn"] * panel["localDownturn"]
    )
    return panel, aligned_pressure


def _modern_pressure_replacement_validation(
    source: pd.DataFrame,
    modern_features: pd.DataFrame,
) -> dict[str, object]:
    rows: list[pd.DataFrame] = []
    for year in sorted(source.loc[source["year"] >= 2000, "year"].unique()):
        train = source.loc[source["year"] <= year - 3].copy()
        original = source.loc[source["year"] == year].copy()
        proxy = original[["year", "iso", "forwardRisk"]].merge(
            modern_features[["iso", "year", *C2_MACRO_PRESSURE_COLUMNS]],
            on=["iso", "year"],
            how="inner",
        )
        if len(train) < 250 or len(proxy) < 6:
            continue
        common_isos = sorted(set(original["iso"]) & set(proxy["iso"]))
        original = original.loc[original["iso"].isin(common_isos)].sort_values(
            "iso"
        )
        proxy = proxy.loc[proxy["iso"].isin(common_isos)].sort_values("iso")
        train["target"], original["target"] = _historical_high_risk_labels(
            train,
            original,
        )
        proxy["target"] = original.set_index("iso")["target"].reindex(
            proxy["iso"]
        ).to_numpy()
        model = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            LogisticRegression(C=0.03, max_iter=2_000),
        )
        model.fit(
            train[list(C2_MACRO_PRESSURE_COLUMNS)],
            train["target"],
        )
        result = proxy[["year", "iso", "target"]].copy()
        result["historicalProbability"] = model.predict_proba(
            original[list(C2_MACRO_PRESSURE_COLUMNS)]
        )[:, 1]
        result["proxyProbability"] = model.predict_proba(
            proxy[list(C2_MACRO_PRESSURE_COLUMNS)]
        )[:, 1]
        rows.append(result)
    frame = pd.concat(rows, ignore_index=True)
    yearly_rank_correlations = []
    yearly_top_quartile_overlap = []
    for _, year in frame.groupby("year"):
        yearly_rank_correlations.append(
            year["historicalProbability"].corr(
                year["proxyProbability"], method="spearman"
            )
        )
        top_count = max(1, int(math.ceil(len(year) * 0.25)))
        historical_top = set(
            year.nlargest(top_count, "historicalProbability")["iso"]
        )
        proxy_top = set(year.nlargest(top_count, "proxyProbability")["iso"])
        yearly_top_quartile_overlap.append(
            len(historical_top & proxy_top) / top_count
        )
    subperiods = []
    for start_year, end_year in ((2000, 2008), (2009, 2017)):
        period = frame.loc[frame["year"].between(start_year, end_year)]
        subperiods.append(
            {
                "startYear": start_year,
                "endYear": end_year,
                "historicalSignal": _risk_classification_metrics(
                    period["target"], period["historicalProbability"]
                ),
                "replacementProxy": _risk_classification_metrics(
                    period["target"], period["proxyProbability"]
                ),
                "probabilityCorrelation": _json_value(
                    period["historicalProbability"].corr(
                        period["proxyProbability"]
                    )
                ),
            }
        )
    historical_metrics = _risk_classification_metrics(
        frame["target"], frame["historicalProbability"]
    )
    proxy_metrics = _risk_classification_metrics(
        frame["target"], frame["proxyProbability"]
    )
    probability_correlation = float(
        frame["historicalProbability"].corr(frame["proxyProbability"])
    )
    direction_agreement = float(
        np.mean(
            (frame["historicalProbability"] >= 0.5)
            == (frame["proxyProbability"] >= 0.5)
        )
    )
    passed = (
        len(frame) >= 250
        and int(frame["iso"].nunique()) >= 14
        and float(proxy_metrics["auc"]) >= 0.65
        and float(proxy_metrics["brier"])
        <= float(historical_metrics["brier"]) + 0.005
        and probability_correlation >= 0.40
        and direction_agreement >= 0.85
        and float(np.nanmedian(yearly_rank_correlations)) >= 0.30
        and float(np.median(yearly_top_quartile_overlap)) >= 0.50
        and all(
            float(period["replacementProxy"]["auc"]) >= 0.54
            for period in subperiods
        )
    )
    return {
        "status": "passed_limited" if passed else "failed",
        "observations": len(frame),
        "countryCount": int(frame["iso"].nunique()),
        "startYear": int(frame["year"].min()),
        "endYear": int(frame["year"].max()),
        "historicalSignal": historical_metrics,
        "replacementProxy": proxy_metrics,
        "probabilityCorrelation": _json_value(probability_correlation),
        "probabilityDirectionAgreement": _json_value(direction_agreement),
        "meanAbsoluteProbabilityDifference": _json_value(
            np.mean(
                np.abs(
                    frame["historicalProbability"]
                    - frame["proxyProbability"]
                )
            )
        ),
        "medianYearlyRankCorrelation": _json_value(
            np.nanmedian(yearly_rank_correlations)
        ),
        "medianYearlyTopQuartileOverlap": _json_value(
            np.median(yearly_top_quartile_overlap)
        ),
        "subperiods": subperiods,
        "gate": {
            "minimumObservations": 250,
            "minimumCountries": 14,
            "minimumProxyAuc": 0.65,
            "maximumBrierDeterioration": 0.005,
            "minimumProbabilityCorrelation": 0.40,
            "minimumDirectionAgreement": 0.85,
            "minimumMedianYearlyRankCorrelation": 0.30,
            "minimumMedianTopQuartileOverlap": 0.50,
            "minimumSubperiodAuc": 0.54,
        },
        "method": "仅用1999年及以前重叠样本完成跨源尺度对齐；2000年后逐年把现代结构压力替换进冻结的历史宏观模型，比较概率路径、排序、高压分组、AUC与Brier。",
    }


def _current_macro_pressure_state(
    historical_pressure: pd.DataFrame,
    historical_financing: pd.DataFrame,
    modern_features: pd.DataFrame,
    bridge_panel: pd.DataFrame,
) -> dict[str, object]:
    pressure_pivot = historical_pressure.pivot_table(
        index="year",
        columns="iso",
        values="pressure",
        aggfunc="last",
    )
    historical_global = pressure_pivot.median(axis=1).where(
        pressure_pivot.notna().sum(axis=1) >= 6
    ).dropna()
    modern_global = (
        modern_features.pivot_table(
            index="year",
            columns="iso",
            values="pressure",
            aggfunc="last",
        )
    )
    modern_count = modern_global.notna().sum(axis=1)
    modern_global = modern_global.median(axis=1).where(
        modern_count >= 12
    ).dropna()
    current_year = int(modern_global.index[-1])
    current_pressure = float(modern_global.iloc[-1])
    slope_3y = float(
        (modern_global.iloc[-1] - modern_global.iloc[-4]) / 3.0
        if len(modern_global) >= 4
        else modern_global.diff().iloc[-1]
    )
    percentile = float((historical_global <= current_pressure).mean())
    level = (
        "high"
        if percentile >= 0.75
        else "low"
        if percentile <= 0.25
        else "middle"
    )
    direction = (
        "rising" if slope_3y >= 0.10 else "falling" if slope_3y <= -0.10 else "stable"
    )
    current = modern_features.loc[
        (modern_features["year"] == current_year)
        & modern_features["pressure"].notna()
    ].copy()
    component_columns = (
        "structural_valuation",
        "structural_leverage",
        "structural_investment",
    )
    financing_column = "oecd_short_real_financing"
    financing_coverage = (
        bridge_panel.loc[bridge_panel[financing_column].notna()]
        .groupby("year")["iso"]
        .nunique()
        .sort_index()
    )
    latest_financing_year = int(financing_coverage.index[-1])
    minimum_financing_countries = 12
    supported_financing = financing_coverage.loc[
        financing_coverage >= minimum_financing_countries
    ]
    latest_supported_financing_year = (
        int(supported_financing.index[-1])
        if not supported_financing.empty
        else None
    )
    historical_financing_pivot = historical_financing.pivot_table(
        index="year",
        columns="iso",
        values="family_financing_conditions",
        aggfunc="last",
    )
    historical_global_financing = historical_financing_pivot.median(
        axis=1
    ).where(historical_financing_pivot.notna().sum(axis=1) >= 6).dropna()
    modern_financing_pivot = bridge_panel.pivot_table(
        index="year",
        columns="iso",
        values=financing_column,
        aggfunc="last",
    )
    modern_financing_count = modern_financing_pivot.notna().sum(axis=1)
    modern_global_financing = modern_financing_pivot.median(axis=1).where(
        modern_financing_count >= minimum_financing_countries
    ).dropna()
    current_financing = float(modern_global_financing.iloc[-1])
    financing_percentile = float(
        (historical_global_financing <= current_financing).mean()
    )
    financing_label = (
        "三年融资脉冲处于历史收紧端"
        if financing_percentile <= 0.25
        else "三年融资脉冲偏紧"
        if financing_percentile <= 0.40
        else "三年融资脉冲处于历史宽松端"
        if financing_percentile >= 0.75
        else "三年融资脉冲偏松"
        if financing_percentile >= 0.60
        else "三年融资脉冲接近中性"
    )
    labels = {
        ("high", "rising"): "结构压力偏高且仍在上行",
        ("high", "falling"): "结构压力仍高但正在回落",
        ("high", "stable"): "结构压力高位盘整",
        ("middle", "rising"): "结构压力中位上行",
        ("middle", "falling"): "结构压力中位回落",
        ("middle", "stable"): "结构压力处于历史中位",
        ("low", "rising"): "结构压力低位修复",
        ("low", "falling"): "结构压力低位继续回落",
        ("low", "stable"): "结构压力处于历史低位",
    }
    return {
        "status": "limited_current_macro_pressure",
        "asOfYear": current_year,
        "countryCount": int(len(current)),
        "minimumCountryCount": 12,
        "pressure": _json_value(current_pressure),
        "historicalPercentile": _json_value(percentile),
        "level": level,
        "direction": direction,
        "slope3Y": _json_value(slope_3y),
        "label": labels[(level, direction)],
        "components": {
            column.removeprefix("structural_"): _json_value(
                current[column].median()
            )
            for column in component_columns
        },
        "financingCoverage": {
            "status": (
                "current_global_coverage_available"
                if int(financing_coverage.loc[latest_financing_year])
                >= minimum_financing_countries
                else "insufficient_current_coverage"
            ),
            "latestDataYear": latest_financing_year,
            "latestDataCountryCount": int(
                financing_coverage.loc[latest_financing_year]
            ),
            "latestSupportedYear": latest_supported_financing_year,
            "minimumCountryCount": minimum_financing_countries,
        },
        "financingState": {
            "status": "limited_current_financing_confirmation",
            "asOfYear": int(modern_global_financing.index[-1]),
            "countryCount": int(
                modern_financing_count.loc[modern_global_financing.index[-1]]
            ),
            "value": _json_value(current_financing),
            "historicalPercentile": _json_value(financing_percentile),
            "label": financing_label,
            "definition": "-Δ3年（OECD三个月短端利率-CPI通胀）",
            "interpretation": "只作为C2确认层，负值代表过去三年实际短端融资条件收紧；不改变住房—按揭核心相位。",
        },
        "countries": _records(
            current[
                [
                    "iso",
                    "year",
                    "pressure",
                    "structural_pressure",
                    *component_columns,
                ]
            ].sort_values("pressure", ascending=False)
        ),
        "riskProbabilityStatus": "blocked_probability_not_calibrated",
        "allocationEligible": False,
        "interpretation": "当前只发布可复核的宏观结构压力位置与方向，不发布国债高风险概率、收益方向或配置权重。",
    }


def _modern_bond_pressure_bridge(
    source: pd.DataFrame,
    jst: pd.DataFrame,
    historical_panel: pd.DataFrame,
    bridge_panel: pd.DataFrame,
) -> dict[str, object]:
    historical_pressure = _country_risk_panel(jst)[
        ["iso", "year", "pressure"]
    ]
    modern_features, _ = _modern_macro_pressure_features(
        historical_panel,
        bridge_panel,
        historical_pressure,
    )
    structure_overlap = _proxy_overlap_validation(
        historical_pressure,
        bridge_panel,
        historical_column="pressure",
        proxy_column="structural_pressure",
        start_year=2000,
        end_year=2020,
    )
    historical_financing = historical_panel[
        ["iso", "year", "family_financing_conditions"]
    ]
    financing_overlap = _proxy_overlap_validation(
        historical_financing,
        bridge_panel,
        historical_column="family_financing_conditions",
        proxy_column="oecd_short_real_financing",
        start_year=2000,
        end_year=2020,
    )
    lending_rate_cross_check = _proxy_overlap_validation(
        historical_financing,
        bridge_panel,
        historical_column="family_financing_conditions",
        proxy_column="lending_rate_real_financing",
        start_year=2000,
        end_year=2020,
    )
    replacement = _modern_pressure_replacement_validation(
        source,
        modern_features,
    )
    current_state = _current_macro_pressure_state(
        historical_pressure,
        historical_financing,
        modern_features,
        bridge_panel,
    )
    structure_passed = (
        structure_overlap["observations"] >= 300
        and structure_overlap["countryCount"] >= 15
        and float(structure_overlap["correlation"]) >= 0.70
        and float(structure_overlap["directionAgreement"]) >= 0.80
        and float(structure_overlap["countryMedianCorrelation"]) >= 0.70
        and float(structure_overlap["countryMedianDirectionAgreement"])
        >= 0.80
    )
    financing_fidelity_passed = (
        financing_overlap["observations"] >= 250
        and financing_overlap["countryCount"] >= 15
        and float(financing_overlap["correlation"]) >= 0.85
        and float(financing_overlap["directionAgreement"]) >= 0.85
    )
    financing_coverage_passed = (
        current_state["financingCoverage"]["status"]
        == "current_global_coverage_available"
    )
    current_state_eligible = (
        structure_passed
        and financing_fidelity_passed
        and financing_coverage_passed
        and current_state["countryCount"] >= current_state["minimumCountryCount"]
    )
    replacement["usage"] = "proxy_fidelity_diagnostic_only"
    replacement["assetMappingEligible"] = False
    return {
        "status": (
            "current_macro_state_available"
            if current_state_eligible
            else "failed"
        ),
        "structureProxyValidation": {
            **structure_overlap,
            "status": "passed_limited" if structure_passed else "failed",
            "gate": {
                "minimumObservations": 300,
                "minimumCountries": 15,
                "minimumCorrelation": 0.70,
                "minimumDirectionAgreement": 0.80,
                "minimumCountryMedianCorrelation": 0.70,
                "minimumCountryMedianDirectionAgreement": 0.80,
            },
        },
        "financingProxyValidation": {
            **financing_overlap,
            "status": (
                "fidelity_and_current_coverage_passed"
                if financing_fidelity_passed and financing_coverage_passed
                else "fidelity_passed_coverage_limited"
                if financing_fidelity_passed
                else "failed"
            ),
            "currentCoverageStatus": current_state["financingCoverage"][
                "status"
            ],
            "definition": "-Δ3年（OECD三个月短端利率-CPI通胀）",
            "gate": {
                "minimumObservations": 250,
                "minimumCountries": 15,
                "minimumCorrelation": 0.85,
                "minimumDirectionAgreement": 0.85,
                "minimumCurrentCountries": 12,
            },
        },
        "lendingRateCrossCheck": lending_rate_cross_check,
        "modelReplacementValidation": replacement,
        "currentState": current_state,
        "currentProbabilityStatus": "blocked_probability_not_calibrated",
        "method": "结构压力由房价租金比水平、家庭信用/GDP和投资占比形成；融资确认使用OECD三个月短端实际利率三年变化，并保留世界银行贷款利率作交叉核验。当前状态资格只依赖跨源一致性和覆盖，不依赖资产风险模型。",
        "caveat": "结构与融资代理可用于观察C2确认状态；冻结模型替换只做口径一致性诊断，不能恢复已失败的资产下行风险通道。",
    }


def _asymmetric_bond_risk_channel(
    frame: pd.DataFrame,
) -> dict[str, object]:
    source = frame.loc[
        (frame["category"] == "跨国国债")
        & (frame["horizonYears"] == 3)
        & frame["forwardRisk"].notna()
    ].copy()
    recursive_rows: list[pd.DataFrame] = []
    for year in sorted(source["year"].unique()):
        if year < 1950:
            continue
        train = source.loc[source["year"] <= year - 3].copy()
        test = source.loc[source["year"] == year].copy()
        if len(train) < 250 or test.empty:
            continue
        train["target"], test["target"] = _historical_high_risk_labels(
            train,
            test,
        )
        result = test[["year", "iso", "target"]].copy()
        for regularization in C2_RISK_PARAMETER_GRID:
            suffix = f"{regularization:.2f}"
            result[f"baseline_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                C2_ASSET_PERSISTENCE_COLUMNS,
                regularization=regularization,
            )
            result[f"candidate_{suffix}"] = _risk_classifier_predictions(
                train,
                test,
                C2_RISK_ARCHITECTURES["asymmetric_pressure"],
                regularization=regularization,
            )
        recursive_rows.append(result)
    recursive = pd.concat(recursive_rows, ignore_index=True)
    parameter_plateau: list[dict[str, object]] = []
    for regularization in C2_RISK_PARAMETER_GRID:
        suffix = f"{regularization:.2f}"
        parameter_plateau.append(
            {
                "regularization": regularization,
                **_risk_model_comparison(
                    recursive,
                    baseline_column=f"baseline_{suffix}",
                    candidate_column=f"candidate_{suffix}",
                ),
            }
        )
    selected_suffix = "0.03"
    recursive_comparison = _risk_model_comparison(
        recursive,
        baseline_column=f"baseline_{selected_suffix}",
        candidate_column=f"candidate_{selected_suffix}",
    )
    subperiods = []
    for start_year, end_year in ((1950, 1984), (1985, 2020)):
        period = recursive.loc[recursive["year"].between(start_year, end_year)]
        subperiods.append(
            {
                "startYear": start_year,
                "endYear": end_year,
                **_risk_model_comparison(
                    period,
                    baseline_column=f"baseline_{selected_suffix}",
                    candidate_column=f"candidate_{selected_suffix}",
                ),
            }
        )

    country_rows: list[pd.DataFrame] = []
    for iso in sorted(source["iso"].unique()):
        train = source.loc[
            (source["iso"] != iso) & (source["year"] <= 1999)
        ].copy()
        test = source.loc[
            (source["iso"] == iso) & (source["year"] >= 2000)
        ].copy()
        held_history = source.loc[
            (source["iso"] == iso) & (source["year"] <= 1996),
            "forwardRisk",
        ].dropna()
        if len(train) < 700 or len(test) < 10 or len(held_history) < 20:
            continue
        train["target"], _ = _historical_high_risk_labels(train, train)
        held_threshold = float(held_history.quantile(0.75))
        test["target"] = (
            (test["forwardRisk"] > 0.0)
            & (test["forwardRisk"] >= held_threshold)
        ).astype(int)
        if train["target"].nunique() < 2 or test["target"].nunique() < 2:
            continue
        result = test[["year", "iso", "target"]].copy()
        result["baseline"] = _risk_classifier_predictions(
            train,
            test,
            C2_ASSET_PERSISTENCE_COLUMNS,
        )
        result["candidate"] = _risk_classifier_predictions(
            train,
            test,
            C2_RISK_ARCHITECTURES["asymmetric_pressure"],
        )
        country_rows.append(result)
    country_holdout = pd.concat(country_rows, ignore_index=True)
    country_comparison = _risk_model_comparison(
        country_holdout,
        baseline_column="baseline",
        candidate_column="candidate",
    )
    country_details = []
    for iso, country in country_holdout.groupby("iso"):
        comparison = _risk_model_comparison(
            country,
            baseline_column="baseline",
            candidate_column="candidate",
        )
        country_details.append(
            {
                "iso": str(iso),
                "observations": len(country),
                "events": int(country["target"].sum()),
                **comparison,
            }
        )
    improved_country_share = float(
        np.mean([float(row["aucDelta"]) > 0.0 for row in country_details])
    )
    parameter_stable = all(
        float(row["candidate"]["auc"]) >= 0.64
        and float(row["aucDelta"]) >= 0.04
        and float(row["brierImprovement"]) > 0.0
        for row in parameter_plateau
    )
    subperiod_stable = all(
        float(row["candidate"]["auc"]) >= 0.60
        and float(row["aucDelta"]) >= 0.03
        and float(row["brierImprovement"]) > 0.0
        for row in subperiods
    )
    passed = (
        len(recursive) >= 1_000
        and float(recursive_comparison["candidate"]["auc"]) >= 0.64
        and float(recursive_comparison["aucDelta"]) >= 0.04
        and float(recursive_comparison["brierImprovement"]) >= 0.005
        and parameter_stable
        and subperiod_stable
        and float(country_comparison["candidate"]["auc"]) >= 0.62
        and float(country_comparison["aucDelta"]) >= 0.08
        and float(country_comparison["brierImprovement"]) >= 0.01
        and improved_country_share >= 0.60
    )
    macro_only = _macro_bond_risk_validation(source)
    return {
        "channelId": "c2_asymmetric_bond_downside_risk_3y",
        "status": "passed_historical_stress" if passed else "failed",
        "publicationStatus": (
            "research_only"
            if passed
            else "rejected_after_risk_definition_audit"
        ),
        "realTimeEligible": False,
        "allocationEligible": False,
        "assetCategory": "跨国国债",
        "horizonYears": 3,
        "target": "未来3年实际国债下行风险是否进入该国自身历史75%高风险区",
        "riskDefinition": "未来期限内负收益的均方根；正收益记为零下行风险。",
        "riskDefinitionAudit": {
            "status": (
                "passed_after_downside_correction"
                if passed
                else "failed_after_downside_correction"
            ),
            "previousDefinition": "正负收益都进入平方风险尺度。",
            "currentDefinition": "只统计负收益的均方根。",
            "finding": (
                "修正后非对称压力仍提供稳定增量。"
                if passed
                else "修正后候选AUC不再优于资产惯性且Brier恶化，旧通过结论撤销。"
            ),
        },
        "architecture": "资产惯性 + 高杠杆后转弱 + 融资收紧 + 全球同步下行",
        "recursiveValidation": recursive_comparison,
        "parameterPlateau": parameter_plateau,
        "subperiods": subperiods,
        "leaveCountryOut2000Plus": {
            **country_comparison,
            "countryCount": len(country_details),
            "improvedCountryShare": _json_value(improved_country_share),
            "countries": country_details,
        },
        "macroOnlyValidation": macro_only,
        "gate": {
            "minimumObservations": 1_000,
            "minimumCandidateAuc": 0.64,
            "minimumAucDelta": 0.04,
            "minimumBrierImprovement": 0.005,
            "parameterPlateauRequired": True,
            "minimumSubperiodAuc": 0.60,
            "minimumCountryHoldoutAuc": 0.62,
            "minimumCountryHoldoutAucDelta": 0.08,
            "minimumImprovedCountryShare": 0.60,
        },
        "currentProbabilityStatus": (
            "blocked_probability_not_calibrated"
            if passed
            else "blocked_downside_risk_channel_failed"
        ),
        "method": "按资产大类诊断非对称压力通道；国债3年候选使用只计负收益的下行风险，并经过四组正则参数、前后子时期和国家留一压力测试。",
        "interpretation": (
            "通道描述地产—信用高压后转弱时的中期国债下行风险环境，不判断国债收益方向。"
            if passed
            else "下行风险口径修正后，地产—信用非对称压力不能稳定改善国债风险排序或概率误差。"
        ),
        "caveat": "现代结构压力和融资条件仍可作为C2宏观确认状态观察，但不能转换为国债风险概率、收益方向或配置权重。",
    }


def _hierarchical_asset_risk_validation(
    asset_universe: pd.DataFrame,
    jst: pd.DataFrame,
    historical_panel: pd.DataFrame,
    bridge_panel: pd.DataFrame,
) -> dict[str, object]:
    frame = _hierarchical_risk_prediction_frame(asset_universe, jst)
    asset_class_validation = _asset_class_specific_validation(frame)
    conditional_propagation = _conditional_propagation_validation(frame)
    bond_risk_channel = _asymmetric_bond_risk_channel(frame)
    bond_source = frame.loc[
        (frame["category"] == "跨国国债")
        & (frame["horizonYears"] == 3)
        & frame["forwardRisk"].notna()
    ].copy()
    bond_risk_channel["modernBridge"] = _modern_bond_pressure_bridge(
        bond_source,
        jst,
        historical_panel,
        bridge_panel,
    )
    bond_risk_channel["currentMacroStateEligible"] = (
        bond_risk_channel["modernBridge"]["status"]
        == "current_macro_state_available"
    )
    risk_channel_passed = (
        bond_risk_channel["status"] == "passed_historical_stress"
    )
    probability_status = (
        "blocked_probability_not_calibrated"
        if risk_channel_passed
        else "blocked_downside_risk_channel_failed"
    )
    bond_risk_channel["currentProbabilityStatus"] = probability_status
    bond_risk_channel["modernBridge"]["currentProbabilityStatus"] = (
        probability_status
    )
    bond_risk_channel["modernBridge"]["currentState"][
        "riskProbabilityStatus"
    ] = probability_status
    bond_risk_channel["modernBridge"]["assetMappingStatus"] = (
        "limited_probability_pending_calibration"
        if risk_channel_passed
        else "blocked_downside_risk_channel_failed"
    )
    if not risk_channel_passed:
        bond_risk_channel["modernBridge"]["caveat"] = (
            "结构压力和融资条件的跨源一致性仍通过，只证明宏观状态可观察；"
            "国债下行风险通道未通过，不能进入概率校准或资产映射。"
        )
    horizons: dict[str, object] = {}
    passed_horizons = 0
    for horizon_years in C2_EVENT_HORIZONS:
        categories: list[dict[str, object]] = []
        prediction_frames: list[pd.DataFrame] = []
        for category in C2_EVENT_ASSET_CATEGORIES:
            validation, predictions = _hierarchical_risk_category_validation(
                frame,
                category=category,
                horizon_years=horizon_years,
            )
            categories.append(validation)
            prediction_frames.append(predictions)
        predictions = pd.concat(prediction_frames, ignore_index=True)
        architectures = {
            architecture: _risk_classification_metrics(
                predictions["target"],
                predictions[architecture],
            )
            for architecture in C2_RISK_ARCHITECTURES
        }
        subperiods: list[dict[str, object]] = []
        for start_year, end_year in ((1950, 1984), (1985, 2020)):
            period = predictions.loc[
                predictions["year"].between(start_year, end_year)
            ]
            subperiods.append(
                {
                    "startYear": start_year,
                    "endYear": end_year,
                    "observations": len(period),
                    "architectures": {
                        architecture: _risk_classification_metrics(
                            period["target"],
                            period[architecture],
                        )
                        for architecture in C2_RISK_ARCHITECTURES
                    },
                }
            )
        persistence = architectures["asset_persistence"]
        hierarchy = architectures["country_hierarchy"]
        auc_delta = float(hierarchy["auc"]) - float(persistence["auc"])
        brier_improvement = float(persistence["brier"]) - float(
            hierarchy["brier"]
        )
        category_support = sum(
            bool(category["incrementalVsPersistence"]["rankingImproved"])
            and bool(
                category["incrementalVsPersistence"][
                    "calibrationImproved"
                ]
            )
            for category in categories
        )
        subperiod_stable = all(
            float(period["architectures"]["country_hierarchy"]["auc"])
            >= 0.55
            for period in subperiods
        )
        passed = (
            len(predictions) >= 1_500
            and float(hierarchy["auc"]) >= 0.60
            and auc_delta >= 0.01
            and brier_improvement >= 0.001
            and category_support >= 2
            and subperiod_stable
        )
        passed_horizons += int(passed)
        horizons[f"{horizon_years}y"] = {
            "horizonYears": horizon_years,
            "status": "passed_limited" if passed else "failed_incremental_gate",
            "architectures": architectures,
            "incrementalVsPersistence": {
                "aucDelta": _json_value(auc_delta),
                "brierImprovement": _json_value(brier_improvement),
                "categorySupport": category_support,
                "categoryCount": len(categories),
                "subperiodStable": subperiod_stable,
            },
            "categories": categories,
            "subperiods": subperiods,
        }
    return {
        "status": "passed_limited" if passed_horizons == 2 else "failed",
        "assetForecastStatus": "blocked",
        "passedHorizons": passed_horizons,
        "horizonCount": len(C2_EVENT_HORIZONS),
        "target": "未来1年或3年下行风险是否进入该国该资产自身历史75%高风险区",
        "riskDefinition": "未来期限内负收益的均方根；正收益记为零下行风险。",
        "architectures": {
            "asset_persistence": "资产自身当前收益、动量与历史风险",
            "global_common": "资产惯性 + 全球C2共同项",
            "country_hierarchy": "全球共同项 + 本国偏离 + 本国按揭信用/融资条件交互",
            "asymmetric_pressure": "资产惯性 + 高杠杆后转弱 + 融资收紧 + 全球同步下行",
        },
        "horizons": horizons,
        "historicalRiskChannels": [bond_risk_channel],
        "assetClassValidation": asset_class_validation,
        "conditionalPropagationValidation": conditional_propagation,
        "passedHistoricalRiskChannels": int(
            risk_channel_passed
        ),
        "gate": {
            "minimumObservations": 1_500,
            "minimumHierarchyAuc": 0.60,
            "minimumAucDeltaVsPersistence": 0.01,
            "minimumBrierImprovement": 0.001,
            "minimumSupportedCategories": 2,
            "minimumSubperiodAuc": 0.55,
        },
        "method": "使用16国JST本国股票、国债和短票长历史；先验证股票、国债、短票独立目标，再固定三种经济传播场景检验条件增量。所有模型使用同一递归年份样本外框架，住房资产被排除。",
        "interpretation": "国家分层只有同时改善风险排序、概率校准、资产大类与跨时期稳定性，才能解除风险预测阻断。",
        "caveat": "风险口径审计已撤销旧3年国债波动通道；独立目标验证仍需通过全样本、参数平台、前后时期和国家留一后才可建立资产通道。",
    }


def _country_clock_asset_mapping(
    asset_universe: pd.DataFrame,
    global_state: pd.DataFrame,
    country_history: pd.DataFrame,
    current_geographic_state: dict[str, object],
) -> dict[str, object]:
    direct_assets = asset_universe.loc[
        (asset_universe["dataIdentity"] == "direct_historical_series")
        & asset_universe["category"].isin(C2_EVENT_ASSET_CATEGORIES)
    ].copy()
    global_turns = build_c2_historical_dating(global_state["activity"])[
        "turningPoints"
    ]
    country_turns: dict[str, list[dict[str, object]]] = {}
    country_ranges: dict[str, dict[str, int]] = {}
    for iso, history in country_history.groupby("iso"):
        activity = (
            history.sort_values("year")
            .drop_duplicates("year", keep="last")
            .set_index("year")["activity"]
            .dropna()
        )
        country_ranges[str(iso)] = {
            "startYear": int(activity.index.min()),
            "endYear": int(activity.index.max()),
            "observations": int(len(activity)),
        }
        if len(activity) >= 30:
            country_turns[str(iso)] = build_c2_historical_dating(activity)[
                "turningPoints"
            ]

    cells: list[dict[str, object]] = []
    for asset_id, asset in direct_assets.groupby("assetId"):
        first = asset.iloc[0]
        iso = str(first["iso"])
        local_turns = country_turns.get(iso, [])
        if not local_turns:
            continue
        for horizon_years in C2_EVENT_HORIZONS:
            for target in C2_EVENT_TARGETS:
                local = _event_clock_statistics(
                    asset,
                    local_turns,
                    horizon_years=horizon_years,
                    target=target,
                )
                global_clock = _event_clock_statistics(
                    asset,
                    global_turns,
                    horizon_years=horizon_years,
                    target=target,
                )
                if local is None or global_clock is None:
                    continue
                local_difference = float(local["eventDifference"])
                global_difference = float(global_clock["eventDifference"])
                cells.append(
                    {
                        "assetId": str(asset_id),
                        "category": str(first["category"]),
                        "name": str(first["name"]),
                        "iso": iso,
                        "horizonYears": horizon_years,
                        "target": target,
                        "localClock": local,
                        "globalClock": global_clock,
                        "localClockStronger": abs(local_difference)
                        > abs(global_difference),
                    }
                )

    cell_frame = pd.DataFrame(cells)
    pooled: list[dict[str, object]] = []
    if not cell_frame.empty:
        cell_frame["localDifference"] = cell_frame["localClock"].map(
            lambda value: float(value["eventDifference"])
        )
        cell_frame["globalDifference"] = cell_frame["globalClock"].map(
            lambda value: float(value["eventDifference"])
        )
        for (category, horizon_years, target), group in cell_frame.groupby(
            ["category", "horizonYears", "target"]
        ):
            pooled.append(
                {
                    "category": str(category),
                    "horizonYears": int(horizon_years),
                    "target": str(target),
                    "countryCount": int(group["iso"].nunique()),
                    "assetCount": int(group["assetId"].nunique()),
                    "localClockStrongerShare": _json_value(
                        group["localClockStronger"].mean()
                    ),
                    "expectedDirectionShare": _json_value(
                        (group["localDifference"] > 0.0).mean()
                    ),
                    "medianLocalDifference": _json_value(
                        group["localDifference"].median()
                    ),
                    "medianGlobalDifference": _json_value(
                        group["globalDifference"].median()
                    ),
                }
            )

    current_by_iso = {
        str(country["iso"]): country
        for country in current_geographic_state["focusCountries"]
    }
    focus_countries: list[dict[str, object]] = []
    for iso, label in C2_FOCUS_COUNTRIES.items():
        country_cells = [cell for cell in cells if cell["iso"] == iso]
        direct_asset_count = int(
            direct_assets.loc[direct_assets["iso"] == iso, "assetId"].nunique()
        )
        history = country_ranges.get(iso)
        current = current_by_iso.get(iso)
        status = (
            "direct_long_history"
            if direct_asset_count >= 3 and iso in country_turns
            else "blocked_short_history"
            if history and history["observations"] < 30
            else "blocked_no_direct_asset"
        )
        headline_cells = [
            cell
            for cell in country_cells
            if cell["category"] == "跨国股票"
            and cell["target"] in C2_EVENT_TARGETS
        ]
        current_phase_assets: list[dict[str, object]] = []
        if status == "direct_long_history" and current:
            phase_history = country_history.loc[
                country_history["iso"] == iso,
                ["year", "phase"],
            ]
            for asset_id, asset in direct_assets.loc[
                direct_assets["iso"] == iso
            ].groupby("assetId"):
                first_asset = asset.iloc[0]
                for horizon_years in C2_EVENT_HORIZONS:
                    statistics = _current_phase_asset_statistics(
                        asset,
                        phase_history,
                        current_phase=str(current["phase"]),
                        horizon_years=horizon_years,
                    )
                    if statistics is None:
                        continue
                    current_phase_assets.append(
                        {
                            "assetId": str(asset_id),
                            "category": str(first_asset["category"]),
                            "name": str(first_asset["name"]),
                            **statistics,
                        }
                    )
        focus_countries.append(
            {
                "iso": iso,
                "name": label,
                "status": status,
                "currentPhase": str(current["phase"]) if current else None,
                "asOfPeriod": str(current["asOfPeriod"]) if current else None,
                "history": history,
                "turnCount": len(country_turns.get(iso, [])),
                "directAssetCount": direct_asset_count,
                "headlineCells": headline_cells,
                "currentPhaseAssets": current_phase_assets,
                "reason": (
                    "2012年后本国住房—信用历史不足，不能形成可靠峰谷样本。"
                    if status == "blocked_short_history"
                    else "当前长期直接资产库没有对应本国资产。"
                    if status == "blocked_no_direct_asset"
                    else None
                ),
            }
        )

    local_stronger_share = (
        float(cell_frame["localClockStronger"].mean())
        if not cell_frame.empty
        else None
    )
    return {
        "status": "historical_mapping_only",
        "assetForecastStatus": "blocked",
        "lookAhead": True,
        "summary": {
            "countryCount": int(cell_frame["iso"].nunique())
            if not cell_frame.empty
            else 0,
            "directAssetCount": int(cell_frame["assetId"].nunique())
            if not cell_frame.empty
            else 0,
            "cellCount": len(cells),
            "localClockStrongerShare": _json_value(local_stronger_share),
        },
        "focusCountries": focus_countries,
        "pooled": pooled,
        "cells": cells,
        "method": "各国先独立识别本国C2峰谷，再把本国股票、国债和短票按距本国峰谷的事件时间对齐；同时用全球C2峰谷计算同资产对照。这样不会把中国、美国、日本和英国硬塞进同一个日历周期。",
        "interpretation": "股票收益使用谷后减峰后，风险使用峰后减谷后；当前相位资产画像使用本国历史上同相位的未来1年和3年实际收益、风险均值。所有结果均为历史条件统计，不代表未来必然兑现。",
        "caveat": "峰谷来自双边滤波共识，含未来信息，只能用于历史映射和校准；当前资产预测仍由因果实时状态的样本外验证决定，不能据此解除阻断。",
    }


def _monthly_series(rows: list[dict[str, object]], value: str) -> pd.Series:
    frame = pd.DataFrame(rows)
    index = pd.PeriodIndex(frame["date"].astype(str), freq="M").to_timestamp("M")
    return pd.Series(pd.to_numeric(frame[value], errors="coerce").to_numpy(), index=index)


def _c2_feature_frame(
    state: pd.DataFrame,
    index: pd.DatetimeIndex,
) -> pd.DataFrame:
    if "date" in state:
        source_index = pd.DatetimeIndex(state["date"]).to_period("M").to_timestamp("M")
    else:
        source_index = pd.to_datetime(state.index.astype(str) + "-12-31")
    source = pd.DataFrame(index=source_index)
    source["C2"] = pd.to_numeric(state["activity"], errors="coerce").to_numpy()
    source["C2_slope"] = pd.to_numeric(state["slope"], errors="coerce").to_numpy()
    source["C2_consensus"] = pd.to_numeric(
        state["slopeConsensus"], errors="coerce"
    ).to_numpy()
    for phase in ("recovery", "expansion", "slowdown"):
        source[f"C2_phase_{phase}"] = (
            state["phase"].astype(str).to_numpy() == phase
        ).astype(float)
    return (
        source[list(C2_FEATURE_COLUMNS)]
        .reindex(source.index.union(index))
        .sort_index()
        .ffill()
        .reindex(index)
    )


def _joint_cycle_features(state: pd.DataFrame) -> pd.DataFrame:
    mapping = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    c3_rows = mapping["cycles"]["C3"]["history"]
    c3 = pd.Series(
        [float(row["value"]) for row in c3_rows],
        index=pd.to_datetime([f"{row['year']}-12-31" for row in c3_rows]),
    ).resample("ME").ffill()
    c1_payload = json.loads(C1_PATH.read_text(encoding="utf-8"))
    c1_rows = [
        (int(year), value)
        for year, value in zip(
            c1_payload["dates"], c1_payload["longWave"], strict=True
        )
        if int(year) >= 1900
    ]
    c1 = pd.Series(
        [value for _, value in c1_rows],
        index=pd.to_datetime(
            [f"{year}-12-31" for year, _ in c1_rows], format="%Y-%m-%d"
        ),
        dtype="float64",
    ).resample("ME").ffill()
    c4_payload = json.loads(C4_PATH.read_text(encoding="utf-8"))
    c4 = _monthly_series(c4_payload["timeline"], "rt_level")
    c5_payload = json.loads(C5_PATH.read_text(encoding="utf-8"))
    c5 = _monthly_series(c5_payload["timeline"], "state")
    c7_payload = json.loads(C7_PATH.read_text(encoding="utf-8"))
    c7 = _monthly_series(c7_payload["timeline"], "state")
    index = pd.date_range("2005-11-30", "2026-07-31", freq="ME")
    c2 = _c2_feature_frame(state, index)
    features = pd.DataFrame(index=index)
    features["C1"] = c1.reindex(index).ffill()
    for column in C2_FEATURE_COLUMNS:
        features[column] = c2[column]
    features["C3"] = c3.reindex(index).ffill()
    features["C4"] = c4.reindex(index).ffill()
    features["C5"] = c5.reindex(index).ffill()
    features["C6_sin"] = np.sin(2.0 * np.pi * index.month / 12.0)
    features["C6_cos"] = np.cos(2.0 * np.pi * index.month / 12.0)
    features["C7"] = c7.reindex(index).ffill()
    return features.dropna()


def _c2_track_features(
    state: pd.DataFrame,
    quarterly_states: dict[str, pd.DataFrame],
    index: pd.DatetimeIndex,
) -> dict[str, pd.DataFrame]:
    return {
        "GLOBAL": _c2_feature_frame(state, index),
        **{
            iso: _c2_feature_frame(country_state, index)
            for iso, country_state in quarterly_states.items()
        },
    }


def _seven_cycle_mapping_contract() -> dict[str, object]:
    return {
        "status": "implemented",
        "definition": "C2资产映射只衡量在C1、C3—C7已进入模型后，全球C2或按资产市场暴露加权C2带来的边际样本外改善。",
        "roles": {
            "C1": "长期结构与估值背景",
            "C2": "住房—按揭活动、财富效应与抵押品通道",
            "C3": "资本开支与产能通道",
            "C4": "库存与工业景气通道",
            "C5": "流动性与融资折现通道",
            "C6": "季节和日历效应",
            "C7": "风险偏好与交易通道",
        },
        "c2FeatureBlock": ["活动水平", "1/2/3年动量", "四相位", "全球与国家暴露轨道"],
        "mappingRule": "先验证资产大类，再验证细分资产；细分结果必须同时满足自身增量、所属大类方向一致和跨路径稳定，不能按行业常识硬映射。",
    }


def _non_overlapping_path_metrics(
    frame: pd.DataFrame,
    baseline_columns: list[str],
    full_columns: list[str],
    *,
    challenger_columns: list[str] | None = None,
    horizon_months: int,
    origin_offset: int,
    minimum_train: int = 96,
) -> dict[str, float | int] | None:
    actual: list[float] = []
    baseline_predictions: list[float] = []
    full_predictions: list[float] = []
    challenger_predictions: list[float] = []
    unconditional_predictions: list[float] = []
    for origin, row in frame.iterrows():
        month_number = int(origin.year * 12 + origin.month)
        if month_number % horizon_months != origin_offset:
            continue
        target = row["target"]
        if not np.isfinite(target):
            continue
        cutoff = (
            origin.to_period("M") - horizon_months
        ).to_timestamp("M")
        train = frame.loc[frame.index <= cutoff].dropna(subset=["target"])
        if len(train) < minimum_train:
            continue
        baseline_model = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=20.0),
        )
        full_model = make_pipeline(
            SimpleImputer(strategy="median"),
            StandardScaler(),
            Ridge(alpha=20.0),
        )
        baseline_model.fit(train[baseline_columns], train["target"])
        full_model.fit(train[full_columns], train["target"])
        challenger_model = None
        if challenger_columns is not None:
            challenger_model = make_pipeline(
                SimpleImputer(strategy="median"),
                StandardScaler(),
                Ridge(alpha=20.0),
            )
            challenger_model.fit(train[challenger_columns], train["target"])
        actual.append(float(target))
        baseline_predictions.append(
            float(baseline_model.predict(row[baseline_columns].to_frame().T)[0])
        )
        full_predictions.append(
            float(full_model.predict(row[full_columns].to_frame().T)[0])
        )
        if challenger_model is not None and challenger_columns is not None:
            challenger_predictions.append(
                float(
                    challenger_model.predict(
                        row[challenger_columns].to_frame().T
                    )[0]
                )
            )
        unconditional_predictions.append(float(train["target"].mean()))
    if len(actual) < 3:
        return None
    actual_array = np.asarray(actual)
    baseline_array = np.asarray(baseline_predictions)
    full_array = np.asarray(full_predictions)
    unconditional_array = np.asarray(unconditional_predictions)
    denominator = float(np.square(actual_array - unconditional_array).sum())
    if denominator <= 1e-12:
        return None
    baseline_r2 = 1.0 - float(
        np.square(actual_array - baseline_array).sum()
    ) / denominator
    full_r2 = 1.0 - float(
        np.square(actual_array - full_array).sum()
    ) / denominator
    result: dict[str, float | int | bool] = {
        "observations": len(actual_array),
        "baselineOosR2": baseline_r2,
        "withC2OosR2": full_r2,
        "incrementalOosR2": full_r2 - baseline_r2,
        "baselineMae": float(np.mean(np.abs(actual_array - baseline_array))),
        "withC2Mae": float(np.mean(np.abs(actual_array - full_array))),
    }
    if challenger_columns is not None:
        challenger_array = np.asarray(challenger_predictions)
        challenger_r2 = 1.0 - float(
            np.square(actual_array - challenger_array).sum()
        ) / denominator
        challenger_mae = float(
            np.mean(np.abs(actual_array - challenger_array))
        )
        result.update(
            {
                "exposureWeightedOosR2": challenger_r2,
                "exposureIncrementalOosR2": challenger_r2 - baseline_r2,
                "exposureDeltaVsGlobalOosR2": challenger_r2 - full_r2,
                "exposureWeightedMae": challenger_mae,
                "exposureBeatsGlobalMae": challenger_mae
                < float(result["withC2Mae"]),
            }
        )
    return result


def _forward_monthly_target(
    returns: pd.Series,
    horizon_months: int,
    target: str,
) -> pd.Series:
    if target == "return":
        return (
            (1.0 + returns)
            .rolling(horizon_months, min_periods=horizon_months)
            .apply(np.prod, raw=True)
            .shift(-horizon_months)
            - 1.0
        )
    return (
        returns.rolling(horizon_months, min_periods=horizon_months)
        .std(ddof=1)
        .shift(-horizon_months)
        * np.sqrt(12.0)
    )


def _joint_asset_cell(
    returns: pd.DataFrame,
    features: pd.DataFrame,
    *,
    exposure_registry: pd.DataFrame,
    c2_track_features: dict[str, pd.DataFrame],
    horizon_months: int,
    target: str,
) -> dict[str, object]:
    baseline_columns = ["C1", "C3", "C4", "C5", "C6_sin", "C6_cos", "C7"]
    c2_columns = list(C2_FEATURE_COLUMNS)
    full_columns = ["C1", *c2_columns, "C3", "C4", "C5", "C6_sin", "C6_cos", "C7"]
    exposure_columns = [f"deviation_{column}" for column in C2_FEATURE_COLUMNS]
    challenger_columns = [
        *full_columns,
        *exposure_columns,
    ]
    exposure_by_asset = exposure_registry.set_index("assetId")
    rows: list[dict[str, object]] = []
    candidate_assets = 0
    direct_country_candidates = 0
    insufficient_country_history = 0
    for category, name in returns.columns:
        asset_id = f"{category}||{name}"
        exposure = exposure_by_asset.loc[asset_id]
        asset_returns = pd.to_numeric(returns[(category, name)], errors="coerce")
        global_frame = features.join(
            asset_returns.rename("assetReturn"),
            how="inner",
        )
        global_frame["target"] = _forward_monthly_target(
            global_frame["assetReturn"], horizon_months, target
        )
        target_observations = int(global_frame["target"].notna().sum())
        if target_observations < 120:
            continue
        candidate_assets += 1
        path_metrics = [
            metrics
            for offset in range(0, horizon_months, 3)
            if (
                metrics := _non_overlapping_path_metrics(
                    global_frame,
                    baseline_columns,
                    full_columns,
                    horizon_months=horizon_months,
                    origin_offset=offset,
                )
            )
            is not None
        ]
        if len(path_metrics) < min(4, horizon_months // 3):
            continue
        baseline_r2_values = np.asarray(
            [float(metrics["baselineOosR2"]) for metrics in path_metrics]
        )
        full_r2_values = np.asarray(
            [float(metrics["withC2OosR2"]) for metrics in path_metrics]
        )
        incremental_values = np.asarray(
            [float(metrics["incrementalOosR2"]) for metrics in path_metrics]
        )
        baseline_mae_values = np.asarray(
            [float(metrics["baselineMae"]) for metrics in path_metrics]
        )
        full_mae_values = np.asarray(
            [float(metrics["withC2Mae"]) for metrics in path_metrics]
        )
        direct_country_track = any(
            track_id != "GLOBAL" for track_id in exposure["c2Weights"]
        )
        row: dict[str, object] = {
            "assetId": asset_id,
            "category": str(category),
            "name": str(name),
            "listingMarket": str(exposure["listingMarket"]),
            "underlyingMarket": str(exposure["underlyingMarket"]),
            "fundingCurrency": str(exposure["fundingCurrency"]),
            "exposureConfidence": str(exposure["exposureConfidence"]),
            "weightBasis": str(exposure["weightBasis"]),
            "c2Weights": exposure["c2Weights"],
            "exposureArchitecture": "global_common_plus_market_deviation",
            "directCountryTrack": direct_country_track,
            "observations": target_observations,
            "pathCount": len(path_metrics),
            "evaluationOrigins": int(
                sum(int(metrics["observations"]) for metrics in path_metrics)
            ),
            "baselineOosR2": _json_value(np.median(baseline_r2_values)),
            "withC2OosR2": _json_value(np.median(full_r2_values)),
            "incrementalOosR2": _json_value(np.median(incremental_values)),
            "positiveFullPathShare": _json_value(
                np.mean(full_r2_values > 0.0)
            ),
            "positiveIncrementPathShare": _json_value(
                np.mean(incremental_values > 0.0)
            ),
            "maeImproved": bool(
                np.median(full_mae_values) < np.median(baseline_mae_values)
            ),
            "exposureStatus": "global_only_no_country_track",
        }
        if direct_country_track:
            direct_country_candidates += 1
            weighted_features = build_weighted_c2_features(
                c2_track_features,
                exposure["c2Weights"],
            )
            deviation_features = weighted_features.subtract(
                c2_track_features["GLOBAL"]
            ).rename(
                columns={
                    column: f"deviation_{column}"
                    for column in C2_FEATURE_COLUMNS
                }
            )
            paired_frame = global_frame.join(
                deviation_features,
                how="inner",
            ).dropna(subset=exposure_columns)
            paired_metrics = [
                metrics
                for offset in range(0, horizon_months, 3)
                if (
                    metrics := _non_overlapping_path_metrics(
                        paired_frame,
                        baseline_columns,
                        full_columns,
                        challenger_columns=challenger_columns,
                        horizon_months=horizon_months,
                        origin_offset=offset,
                    )
                )
                is not None
            ]
            if len(paired_metrics) >= min(4, horizon_months // 3):
                exposure_r2_values = np.asarray(
                    [
                        float(metrics["exposureWeightedOosR2"])
                        for metrics in paired_metrics
                    ]
                )
                exposure_increment_values = np.asarray(
                    [
                        float(metrics["exposureIncrementalOosR2"])
                        for metrics in paired_metrics
                    ]
                )
                exposure_delta_values = np.asarray(
                    [
                        float(metrics["exposureDeltaVsGlobalOosR2"])
                        for metrics in paired_metrics
                    ]
                )
                exposure_mae_values = np.asarray(
                    [
                        float(metrics["exposureWeightedMae"])
                        for metrics in paired_metrics
                    ]
                )
                paired_global_mae_values = np.asarray(
                    [float(metrics["withC2Mae"]) for metrics in paired_metrics]
                )
                row.update(
                    {
                        "exposureStatus": "validated_same_sample",
                        "exposureObservations": int(
                            paired_frame["target"].notna().sum()
                        ),
                        "exposurePathCount": len(paired_metrics),
                        "exposureEvaluationOrigins": int(
                            sum(
                                int(metrics["observations"])
                                for metrics in paired_metrics
                            )
                        ),
                        "exposureWeightedOosR2": _json_value(
                            np.median(exposure_r2_values)
                        ),
                        "exposureIncrementalOosR2": _json_value(
                            np.median(exposure_increment_values)
                        ),
                        "exposureDeltaVsGlobalOosR2": _json_value(
                            np.median(exposure_delta_values)
                        ),
                        "positiveExposurePathShare": _json_value(
                            np.mean(exposure_r2_values > 0.0)
                        ),
                        "exposureBeatsGlobalPathShare": _json_value(
                            np.mean(exposure_delta_values > 0.0)
                        ),
                        "exposureMaeImprovedVsGlobal": bool(
                            np.median(exposure_mae_values)
                            < np.median(paired_global_mae_values)
                        ),
                    }
                )
            else:
                insufficient_country_history += 1
                row["exposureStatus"] = "insufficient_country_track_history"
                row["exposurePathCount"] = len(paired_metrics)
        rows.append(row)
    increments = np.asarray(
        [float(row["incrementalOosR2"]) for row in rows], dtype="float64"
    )
    full_r2_values = np.asarray(
        [float(row["withC2OosR2"]) for row in rows], dtype="float64"
    )
    direct_rows = [
        row for row in rows if row["exposureStatus"] == "validated_same_sample"
    ]
    exposure_r2_values = np.asarray(
        [float(row["exposureWeightedOosR2"]) for row in direct_rows],
        dtype="float64",
    )
    exposure_increment_values = np.asarray(
        [float(row["exposureIncrementalOosR2"]) for row in direct_rows],
        dtype="float64",
    )
    exposure_delta_values = np.asarray(
        [float(row["exposureDeltaVsGlobalOosR2"]) for row in direct_rows],
        dtype="float64",
    )
    category_summaries: dict[str, object] = {}
    for category, category_rows in pd.DataFrame(rows).groupby("category") if rows else []:
        category_summaries[str(category)] = {
            "assetCount": int(len(category_rows)),
            "positiveFullOosR2Share": _json_value(
                (category_rows["withC2OosR2"] > 0.0).mean()
            ),
            "medianFullOosR2": _json_value(
                category_rows["withC2OosR2"].median()
            ),
            "positiveIncrementShare": _json_value(
                (category_rows["incrementalOosR2"] > 0.0).mean()
            ),
            "medianIncrementalOosR2": _json_value(
                category_rows["incrementalOosR2"].median()
            ),
            "maeImprovedShare": _json_value(category_rows["maeImproved"].mean()),
        }
    global_passed = (
        len(rows) >= 70
        and float(np.median(full_r2_values)) > 0.0
        and float(np.mean(full_r2_values > 0.0)) >= 0.55
        and float(np.median(increments)) > 0.0
        and float(np.mean(increments > 0.0)) >= 0.55
        and float(np.mean([row["maeImproved"] for row in rows])) >= 0.55
    ) if rows else False
    exposure_passed = (
        len(direct_rows) >= 70
        and float(np.median(exposure_r2_values)) > 0.0
        and float(np.mean(exposure_r2_values > 0.0)) >= 0.55
        and float(np.median(exposure_increment_values)) > 0.0
        and float(np.mean(exposure_increment_values > 0.0)) >= 0.55
        and float(np.median(exposure_delta_values)) > 0.0
        and float(np.mean(exposure_delta_values > 0.0)) >= 0.55
        and float(
            np.mean(
                [row["exposureMaeImprovedVsGlobal"] for row in direct_rows]
            )
        )
        >= 0.55
    ) if direct_rows else False
    status = (
        "passed_limited"
        if global_passed or exposure_passed
        else "insufficient_non_overlapping_history"
        if candidate_assets and not rows
        else "failed"
    )
    return {
        "status": status,
        "candidateAssetCount": candidate_assets,
        "assetCount": len(rows),
        "directCountryCandidateCount": direct_country_candidates,
        "exposureValidatedAssetCount": len(direct_rows),
        "insufficientCountryHistoryCount": insufficient_country_history,
        "positiveFullOosR2Count": int((full_r2_values > 0.0).sum()),
        "positiveFullOosR2Share": _json_value(
            np.mean(full_r2_values > 0.0) if len(full_r2_values) else None
        ),
        "medianFullOosR2": _json_value(
            np.median(full_r2_values) if len(full_r2_values) else None
        ),
        "positiveIncrementCount": int((increments > 0.0).sum()),
        "positiveIncrementShare": _json_value(
            np.mean(increments > 0.0) if len(increments) else None
        ),
        "medianIncrementalOosR2": _json_value(
            np.median(increments) if len(increments) else None
        ),
        "maeImprovedShare": _json_value(
            np.mean([row["maeImproved"] for row in rows]) if rows else None
        ),
        "categories": category_summaries,
        "assets": rows,
        "modelComparison": {
            "globalC2": {
                "passed": global_passed,
                "assetCount": len(rows),
                "positiveOosR2Share": _json_value(
                    np.mean(full_r2_values > 0.0)
                    if len(full_r2_values)
                    else None
                ),
                "medianOosR2": _json_value(
                    np.median(full_r2_values) if len(full_r2_values) else None
                ),
            },
            "exposureWeightedC2": {
                "architecture": "全球共同C2 + 标的市场C2偏离项",
                "passed": exposure_passed,
                "assetCount": len(direct_rows),
                "positiveOosR2Share": _json_value(
                    np.mean(exposure_r2_values > 0.0)
                    if len(exposure_r2_values)
                    else None
                ),
                "medianOosR2": _json_value(
                    np.median(exposure_r2_values)
                    if len(exposure_r2_values)
                    else None
                ),
                "positiveIncrementShare": _json_value(
                    np.mean(exposure_increment_values > 0.0)
                    if len(exposure_increment_values)
                    else None
                ),
                "medianIncrementalOosR2": _json_value(
                    np.median(exposure_increment_values)
                    if len(exposure_increment_values)
                    else None
                ),
                "shareBeatingGlobalOosR2": _json_value(
                    np.mean(exposure_delta_values > 0.0)
                    if len(exposure_delta_values)
                    else None
                ),
                "medianOosR2DeltaVsGlobal": _json_value(
                    np.median(exposure_delta_values)
                    if len(exposure_delta_values)
                    else None
                ),
                "shareBeatingGlobalMae": _json_value(
                    np.mean(
                        [
                            row["exposureMaeImprovedVsGlobal"]
                            for row in direct_rows
                        ]
                    )
                    if direct_rows
                    else None
                ),
            },
        },
        "horizonMonths": horizon_months,
        "target": target,
        "evaluation": "按季度起点拆成多条路径；同一路径的预测起点间隔等于目标期限，因此目标不重叠。错位模型保留全球C2共同项，再加入标的市场C2减全球C2的偏离项；两种模型使用完全相同的资产和截点。",
        "reason": (
            "20年月频资产样本不足以形成至少四条可用的36个月非重叠递归路径。"
            if status == "insufficient_non_overlapping_history"
            else None
        ),
    }


def _joint_asset_mapping(
    state: pd.DataFrame,
    quarterly_states: dict[str, pd.DataFrame],
) -> dict[str, object]:
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.DatetimeIndex(returns.index).to_period("M").to_timestamp("M")
    features = _joint_cycle_features(state)
    exposure_registry = build_c2_asset_exposure_registry(
        returns.columns,
        C2_EXPOSURE_PATH,
    )
    track_features = _c2_track_features(
        state,
        quarterly_states,
        features.index,
    )
    cells = {
        "12mReturn": _joint_asset_cell(
            returns,
            features,
            exposure_registry=exposure_registry,
            c2_track_features=track_features,
            horizon_months=12,
            target="return",
        ),
        "36mReturn": _joint_asset_cell(
            returns,
            features,
            exposure_registry=exposure_registry,
            c2_track_features=track_features,
            horizon_months=36,
            target="return",
        ),
        "12mRisk": _joint_asset_cell(
            returns,
            features,
            exposure_registry=exposure_registry,
            c2_track_features=track_features,
            horizon_months=12,
            target="risk",
        ),
        "36mRisk": _joint_asset_cell(
            returns,
            features,
            exposure_registry=exposure_registry,
            c2_track_features=track_features,
            horizon_months=36,
            target="risk",
        ),
    }
    passed_cells = sum(
        cell["modelComparison"]["exposureWeightedC2"]["passed"]
        for cell in cells.values()
    )
    exposure_rows = exposure_registry.to_dict(orient="records")
    track_asset_counts = {
        track_id: sum(track_id in row["c2Weights"] for row in exposure_rows)
        for track_id in ("GLOBAL", "CHN", "USA", "JPN", "GBR")
    }
    return {
        "status": "passed_limited" if passed_cells >= 3 else "failed",
        "passedCells": passed_cells,
        "exposurePassedCells": passed_cells,
        "globalPassedCells": sum(
            cell["modelComparison"]["globalC2"]["passed"]
            for cell in cells.values()
        ),
        "cellCount": len(cells),
        "cells": cells,
        "method": "在同一月频样本和同一递归截点下，先用C1、C3—C7预测未来12/36个月资产收益和风险，再比较全球C2与“全球共同项+标的市场偏离项”；只有绝对样本外表现和相对全球增量同时通过才解除阻断。",
        "gate": {
            "minimumPassedCells": 3,
            "cellGate": {
                "minimumAssets": 70,
                "minimumPositiveFullOosR2Share": 0.55,
                "minimumMedianFullOosR2": 0.0,
                "minimumPositiveIncrementShare": 0.55,
                "minimumMedianIncrementalOosR2": 0.0,
                "minimumMaeImprovedShare": 0.55,
                "minimumExposureAssets": 70,
                "minimumShareBeatingGlobalOosR2": 0.55,
                "minimumMedianOosR2DeltaVsGlobal": 0.0,
                "minimumShareBeatingGlobalMae": 0.55,
            },
        },
        "exposureRegistry": {
            "status": "implemented",
            "version": "c2-asset-exposure-v1",
            "assetCount": len(exposure_rows),
            "directCountryTrackAssets": sum(
                any(track_id != "GLOBAL" for track_id in row["c2Weights"])
                for row in exposure_rows
            ),
            "trackAssetCounts": track_asset_counts,
            "fields": [
                "上市地",
                "标的市场",
                "收入来源代理",
                "生产地代理",
                "融资币种",
                "利率敏感度",
                "C2轨道权重",
            ],
            "assets": exposure_rows,
            "method": "模型按标的市场而非ETF上市地选择国家C2偏离项；收入、生产地和融资币种没有可靠成分股数据时明确标为未知或代理，不参与本轮权重拟合。",
        },
        "caveat": "这是七周期联合模型中的边际统计贡献，不是经济因果归因；不得把资产全部涨跌归给C2。",
        "framework": _seven_cycle_mapping_contract(),
    }


def build_payload() -> dict[str, object]:
    (
        jst,
        state,
        combined_panel,
        metadata,
        quarterly_states,
        historical_panel,
        bridge_panel,
    ) = _combined_c2_panel()
    realtime_turning_points = date_c2_turning_points(state)
    historical_dating = build_c2_historical_dating(state["activity"])
    family_states = _global_family_states(combined_panel)
    family_summary = _family_state_summary(
        family_states,
        as_of_year=int(state.index[-1]),
    )
    latest = state.iloc[-1]
    transition_target = future_transition_target(state["phase"], 3)
    transition_rate = transition_target.groupby(state["phase"]).mean().to_dict()
    country_risk_panel = _country_risk_panel(jst)
    phase_history = (
        state.reset_index(names="year")
        .rename(columns={"activity": "value"})
        [["year", "phase", "value", "slope"]]
    )
    asset_universe = build_asset_universe(jst)
    historical_asset_mapping = build_asset_mapping(
        asset_universe,
        phase_history,
        "C2",
    )
    geographic_state, country_history, region_history = _direct_geographic_state(
        combined_panel,
        state,
        quarterly_states,
    )
    transition_evidence = _transition_evidence(
        state,
        family_summary,
        geographic_state,
    )
    eligible_asset_ids = {
        str(asset["assetId"])
        for asset in historical_asset_mapping["assets"]
        if asset["eligible"]
    }
    historical_asset_mapping["geographicValidation"] = (
        build_c2_geographic_asset_validation(
            asset_universe,
            phase_history,
            country_history,
            region_history,
            eligible_asset_ids=eligible_asset_ids,
        )
    )
    historical_asset_mapping["interactionValidation"] = {
        "status": "not_run_geographic_gate_failed",
        "preregisteredCandidates": [
            "C2 × 估值",
            "C2 × 实际利率",
            "C2 × 信用条件",
        ],
        "reason": "直接国家/区域C2尚未通过绝对资产预测门槛，停止后续交互搜索，避免数据挖掘。",
    }
    historical_asset_mapping.update(
        {
            "title": "C2 直接相位长样本资产映射",
            "stateDefinition": "住房—按揭活动核心的水平、1/2/3年动量共识与两期转相确认。",
            "assetForecastStatus": "blocked",
            "mappingFramework": _seven_cycle_mapping_contract(),
        }
    )
    joint_asset_mapping = _joint_asset_mapping(state, quarterly_states)
    joint_asset_mapping["countryClockMapping"] = _country_clock_asset_mapping(
        asset_universe,
        state,
        country_history,
        geographic_state,
    )
    joint_asset_mapping["hierarchicalRiskValidation"] = (
        _hierarchical_asset_risk_validation(
            asset_universe,
            jst,
            historical_panel,
            bridge_panel,
        )
    )
    return {
        "meta": {
            "generated": pd.Timestamp.now(tz="Asia/Shanghai").isoformat(),
            "asOfPeriod": metadata["asOfPeriod"],
            "modelVersion": "c2-conditional-propagation-v12",
        },
        "architecture": {
            "activityCore": ["实际房价/租金动量", "按揭信用脉冲"],
            "confirmation": ["建设/总投资脉冲", "实际融资条件"],
            "structuralPressure": ["房价租金估值", "按揭杠杆", "投资占比"],
            "propagation": ["GDP", "消费", "就业", "实际工资"],
            "geography": "全球共同项 + 区域偏离项 + 本国偏离项 + 预注册分布滞后",
            "periodRule": "200个月只保留为弱经验先验；实时状态不强制周期长度，历史定年由多参数滤波共识识别。",
            "mappingRule": "收益点预测继续阻断；股票、国债和短票分别定义目标，并预注册高杠杆后融资转松、地产下行叠加衰退、住房复苏叠加信用扩张三种传播场景。只有完整样本外条件增量通过才下沉细分资产。",
        },
        "state": {
            "status": "limited_current_state",
            "current": {
                "year": int(state.index[-1]),
                "phase": str(latest["phase"]),
                "rawPhase": str(latest["rawPhase"]),
                "activity": _json_value(latest["activity"]),
                "slope": _json_value(latest["slope"]),
                "curvature": _json_value(latest["curvature"]),
                "slopeConsensus": _json_value(latest["slopeConsensus"]),
                "slope1Y": _json_value(latest["slope1Y"]),
                "slope2Y": _json_value(latest["slope2Y"]),
                "slope3Y": _json_value(latest["slope3Y"]),
                "phaseDurationYears": int(latest["phaseDurationYears"]),
                "countryCount": int(latest["countryCount"]),
                "transitionCandidate": transition_evidence["status"] == "candidate",
            },
            "history": _records(state.reset_index(names="year")),
            "turningPoints": realtime_turning_points,
            "transitionEvidence": transition_evidence,
            "familyStates": family_summary,
            "historicalThreeYearTransitionRateByPhase": {
                phase: _json_value(value) for phase, value in transition_rate.items()
            },
            "method": "对住房—按揭活动核心做因果稳健标准化；由水平和1/2/3年动量共识直接形成四相位，连续两年确认后才转相，不强制固定正弦波和固定200个月长度。",
        },
        "historicalDating": historical_dating,
        "expertCalibration": _turning_point_validation(
            jst,
            historical_dating["turningPoints"],
        ),
        "geographicState": geographic_state,
        "tailRiskValidation": {
            "1y": _risk_validation(country_risk_panel, 1),
            "3y": _risk_validation(country_risk_panel, 3),
        },
        "historicalAssetMapping": historical_asset_mapping,
        "jointAssetMapping": joint_asset_mapping,
        "governance": {
            "allowed": ["当前宽状态", "转相候选", "历史峰谷", "宏观结构与融资确认", "七周期联合模型中的预注册条件交互"],
            "notAllowed": ["精确200个月周期承诺", "精确拐点承诺", "单独C2资产收益预测", "单资产精确风险预测", "继续扩充C2单周期资产特征搜索", "把统计贡献称为因果归因"],
        },
        "references": [
            {
                "title": "The financial cycle and macroeconomics: What have we learnt?",
                "doi": "10.1016/j.jbankfin.2013.07.031",
            },
            {
                "title": "Characterising the Financial Cycle: A Multivariate and Time-Varying Approach",
                "doi": "10.2139/ssrn.2664126",
            },
            {
                "title": "Financial cycles: Characterisation and real-time measurement",
                "doi": "10.1016/j.jimonfin.2019.102082",
            },
            {
                "title": "Credit Booms Gone Bust",
                "doi": "10.1257/aer.102.2.1029",
            },
            {
                "title": "The Great Mortgaging",
                "doi": "10.3386/w20501",
            },
        ],
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(f"Wrote: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
