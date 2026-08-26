#!/usr/bin/env python3
"""Bridge the approved C4 pseudo-realtime state with current PMI and PPI data."""

from __future__ import annotations

import argparse
from datetime import date
import json
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
PMI_FIELDS = (
    "PMI010400",
    "PMI010500",
    "PMI010700",
    "PMI011400",
    "PMI011500",
    "PMI010900",
    "PMI011000",
    "PMI011200",
    "PMI011300",
)


def _phase(level: float, slope: float) -> str:
    if level >= 0:
        return "expansion" if slope >= 0 else "downturn"
    return "recovery" if slope >= 0 else "contraction"


def _angle(level: float, slope: float) -> float:
    omega = 2.0 * math.pi / 42.0
    return float((math.degrees(math.atan2(slope / omega, -level)) + 360.0) % 360.0)


def _model(alpha: float):
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha))


def _month_index(values: pd.Series) -> pd.DatetimeIndex:
    return pd.to_datetime(values.astype(str), format="%Y%m").dt.to_period("M").dt.to_timestamp("M")


def fetch_c4_features() -> pd.DataFrame:
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is required for the C4 realtime bridge")
    import tushare as ts

    ts.set_token(token)
    pro = ts.pro_api()
    pmi = pro.cn_pmi()
    ppi = pro.cn_ppi()
    pmi.index = _month_index(pmi["MONTH"])
    ppi.index = _month_index(ppi["month"])
    pmi = pmi.sort_index()
    ppi = ppi.sort_index()
    features = pd.DataFrame(index=pmi.index)
    for field in PMI_FIELDS:
        series = pd.to_numeric(pmi[field], errors="coerce")
        features[field] = series
        features[f"{field}_d1"] = series.diff()
        features[f"{field}_d3"] = series.diff(3)
    ppi_yoy = pd.to_numeric(ppi["ppi_yoy"], errors="coerce").reindex(features.index)
    features["ppi_yoy"] = ppi_yoy
    features["ppi_yoy_d1"] = ppi_yoy.diff()
    features["ppi_yoy_d3"] = ppi_yoy.diff(3)
    return features.sort_index()


def _timeline_series(payload: dict[str, Any]) -> tuple[pd.Series, pd.Series]:
    timeline = pd.DataFrame(payload["timeline"])
    timeline.index = pd.PeriodIndex(timeline["date"], freq="M").to_timestamp("M")
    observed = pd.to_numeric(timeline["observed"], errors="coerce")
    state = pd.to_numeric(timeline["rt_level"], errors="coerce")
    return observed, state


def _state_rows(
    observed: pd.Series,
    state: pd.Series,
    end_index: int,
) -> tuple[list[list[float]], list[float]]:
    rows: list[list[float]] = []
    targets: list[float] = []
    for index in range(6, end_index + 1):
        values = [
            observed.iloc[index],
            observed.iloc[index - 1],
            observed.iloc[index - 3],
            *[state.iloc[index - lag] for lag in range(1, 7)],
            state.iloc[index - 1] - state.iloc[index - 4],
        ]
        if any(pd.isna(value) for value in values):
            continue
        rows.append([float(value) for value in values])
        targets.append(float(state.iloc[index]))
    return rows, targets


def _recursive_state(
    model: Any,
    observed_history: list[float],
    state_history: list[float],
    future_observed: list[float],
) -> list[float]:
    combined_observed = observed_history + future_observed
    states = list(state_history)
    origin = len(state_history) - 1
    for horizon in range(1, len(future_observed) + 1):
        index = origin + horizon
        row = [
            combined_observed[index],
            combined_observed[index - 1],
            combined_observed[index - 3],
            *[states[index - lag] for lag in range(1, 7)],
            states[index - 1] - states[index - 4],
        ]
        states.append(float(model.predict([row])[0]))
    return states[-len(future_observed) :]


def _validate_bridge(
    features: pd.DataFrame,
    observed: pd.Series,
    state: pd.Series,
) -> dict[str, Any]:
    residuals: dict[int, list[float]] = {horizon: [] for horizon in range(1, 7)}
    phase_hits: dict[int, list[bool]] = {horizon: [] for horizon in range(1, 7)}
    origins = list(range(156, len(state) - 6, 3))
    used_origins = 0
    for origin in origins:
        origin_date = state.index[origin]
        future_dates = state.index[origin + 1 : origin + 7]
        observation_training = features.join(observed.rename("observed")).loc[:origin_date].dropna()
        future_features = features.reindex(future_dates)
        if len(observation_training) < 60 or future_features.isna().any(axis=None):
            continue
        observation_model = _model(10.0)
        observation_model.fit(
            observation_training.drop(columns="observed"),
            observation_training["observed"],
        )
        predicted_observed = observation_model.predict(future_features).tolist()
        state_rows, state_targets = _state_rows(observed, state, origin)
        state_model = _model(5.0)
        state_model.fit(state_rows, state_targets)
        predicted_states = _recursive_state(
            state_model,
            observed.iloc[: origin + 1].astype(float).tolist(),
            state.iloc[: origin + 1].astype(float).tolist(),
            predicted_observed,
        )
        used_origins += 1
        current = float(state.iloc[origin])
        for horizon, predicted in enumerate(predicted_states, start=1):
            actual = float(state.iloc[origin + horizon])
            residuals[horizon].append(actual - predicted)
            phase_hits[horizon].append(
                _phase(predicted, predicted - current)
                == _phase(actual, actual - current)
            )
    if used_origins < 8:
        raise RuntimeError("Insufficient historical cutoffs for C4 bridge validation")
    horizons = {
        str(horizon): {
            "mae": float(np.mean(np.abs(residuals[horizon]))),
            "phase_accuracy": float(np.mean(phase_hits[horizon])),
            "residual_q10": float(np.quantile(residuals[horizon], 0.1)),
            "residual_q90": float(np.quantile(residuals[horizon], 0.9)),
        }
        for horizon in residuals
    }
    return {
        "origins": used_origins,
        "horizons": horizons,
        "six_month_mae": horizons["6"]["mae"],
        "six_month_phase_accuracy": horizons["6"]["phase_accuracy"],
        "publishable_bridge": (
            horizons["6"]["mae"] <= 0.15
            and horizons["6"]["phase_accuracy"] >= 0.65
        ),
    }


def build_bridge(
    realtime_payload: dict[str, Any],
    features: pd.DataFrame,
    *,
    through: str | pd.Timestamp | None = None,
) -> dict[str, Any]:
    observed, state = _timeline_series(realtime_payload)
    features = features.sort_index()
    target_end = pd.Timestamp(through) if through is not None else features.dropna().index.max()
    target_end = target_end.to_period("M").to_timestamp("M")
    bridge_dates = pd.date_range(state.index[-1] + pd.offsets.MonthEnd(1), target_end, freq="ME")
    validation = _validate_bridge(features, observed, state)
    if not validation["publishable_bridge"]:
        raise RuntimeError("C4 bridge failed historical cutoff validation")
    if bridge_dates.empty:
        return {**realtime_payload, "bridge_validation": validation}
    observation_training = features.join(observed.rename("observed")).loc[: state.index[-1]].dropna()
    bridge_features = features.reindex(bridge_dates)
    if bridge_features.isna().any(axis=None):
        missing_dates = bridge_features.index[bridge_features.isna().any(axis=1)]
        raise RuntimeError(f"C4 bridge features incomplete at {missing_dates.strftime('%Y-%m').tolist()}")
    observation_model = _model(10.0)
    observation_model.fit(
        observation_training.drop(columns="observed"),
        observation_training["observed"],
    )
    predicted_observed = observation_model.predict(bridge_features).tolist()
    state_rows, state_targets = _state_rows(observed, state, len(state) - 1)
    state_model = _model(5.0)
    state_model.fit(state_rows, state_targets)
    predicted_states = _recursive_state(
        state_model,
        observed.astype(float).tolist(),
        state.astype(float).tolist(),
        predicted_observed,
    )
    timeline = list(realtime_payload["timeline"])
    previous_state = float(state.iloc[-1])
    previous_phase = timeline[-1].get("confirmed_phase") or timeline[-1].get("rt_phase")
    raw_phases: list[str] = []
    for horizon, (bridge_date, observed_value, state_value) in enumerate(
        zip(bridge_dates, predicted_observed, predicted_states),
        start=1,
    ):
        horizon_metrics = validation["horizons"][str(min(horizon, 6))]
        low = state_value + horizon_metrics["residual_q10"]
        high = state_value + horizon_metrics["residual_q90"]
        slope = state_value - previous_state
        phase = _phase(state_value, slope)
        raw_phases.append(phase)
        uncertainty = max(0.01, (high - low) / 2.0)
        confidence = float(np.clip(1.0 - uncertainty / 0.8, 0.2, 0.72))
        confirmed_phase = previous_phase
        if len(raw_phases) >= 2 and raw_phases[-1] == raw_phases[-2] and confidence >= 0.35:
            confirmed_phase = phase
        timeline.append(
            {
                "date": bridge_date.strftime("%Y-%m"),
                "observed": round(float(observed_value), 5),
                "observed_status": "indicator_family_bridge",
                "rt_level": round(float(state_value), 5),
                "rt_low": round(float(low), 5),
                "rt_high": round(float(high), 5),
                "rt_angle": round(_angle(state_value, slope), 5),
                "phase_concentration": None,
                "rt_uncertainty": round(float(uncertainty), 5),
                "confidence": round(confidence, 5),
                "family_coverage": 1.0,
                "rt_phase": phase,
                "confirmed_phase": confirmed_phase,
                "retro_factor": None,
                "retro_low": None,
                "retro_high": None,
                "retro_phase_angle": None,
                "retro_display_reliability": None,
            }
        )
        previous_state = state_value
        previous_phase = confirmed_phase
    latest = timeline[-1]
    return {
        **realtime_payload,
        "meta": {
            **realtime_payload["meta"],
            "generated": date.today().isoformat(),
            "status": "pseudo_realtime_plus_validated_indicator_bridge",
            "bridge_method": "Tushare PMI/PPI observation Ridge + recursive state Ridge",
            "bridge_data_identity": "latest-restated macro observations, not true release vintage",
            "bridge_start": bridge_dates[0].strftime("%Y-%m"),
            "bridge_end": bridge_dates[-1].strftime("%Y-%m"),
        },
        "timeline": timeline,
        "latest": {
            "date": latest["date"],
            "rt_level": latest["rt_level"],
            "rt_low": latest["rt_low"],
            "rt_high": latest["rt_high"],
            "rt_angle": latest["rt_angle"],
            "rt_phase": latest["rt_phase"],
            "confidence": latest["confidence"],
            "retro_level": None,
            "retro_angle": None,
            "retro_publishable": False,
        },
        "bridge_validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--through")
    args = parser.parse_args()
    realtime_payload = json.loads(args.input.read_text(encoding="utf-8"))
    payload = build_bridge(
        realtime_payload,
        fetch_c4_features(),
        through=args.through,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "latest": payload["latest"],
                "output": str(args.output),
                "validation": payload["bridge_validation"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
