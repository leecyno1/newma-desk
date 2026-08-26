"""Recompute C4 asset return and risk statistics from the refreshed asset panel."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
HISTORICAL_PATH = (
    PROJECT_ROOT / "output" / "c4_c5_phase_display_prototype_2026-07-19.json"
)
REALTIME_PATH = PROJECT_ROOT / "output" / "c4_realtime_bridge_latest.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c4_asset_statistics_current.json"
PHASES = ("recovery", "expansion", "downturn", "contraction")


def phase_from_angle(angle: float) -> str:
    normalized = angle % 360.0
    if normalized < 90.0:
        return "recovery"
    if normalized < 180.0:
        return "expansion"
    if normalized < 270.0:
        return "downturn"
    return "contraction"


def _month_end(value: str | pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(value).to_period("M").to_timestamp("M")


def build_c4_state(
    historical: dict[str, object],
    realtime: dict[str, object],
) -> pd.DataFrame:
    historical_rows = historical["C4"]["cycle"]
    history = pd.DataFrame(
        {
            "date": [_month_end(row["date"]) for row in historical_rows],
            "factor": [float(row["factor"]) for row in historical_rows],
            "phase": [phase_from_angle(float(row["phase_angle"])) for row in historical_rows],
            "cycle_identity": "latest_historical",
        }
    ).set_index("date")

    timeline = pd.DataFrame(realtime["timeline"])
    timeline.index = pd.DatetimeIndex(pd.to_datetime(timeline["date"])).to_period(
        "M"
    ).to_timestamp("M")
    overlap = timeline.dropna(subset=["retro_factor", "rt_level"])
    design = sm.add_constant(pd.to_numeric(overlap["rt_level"], errors="coerce"))
    alignment = sm.OLS(
        pd.to_numeric(overlap["retro_factor"], errors="coerce"),
        design,
        missing="drop",
    ).fit()
    bridge = timeline.loc[timeline.index > history.index.max()].copy()
    if bridge.empty:
        return history
    bridge_factor = alignment.predict(
        sm.add_constant(
            pd.to_numeric(bridge["rt_level"], errors="coerce"),
            has_constant="add",
        )
    )
    bridge_state = pd.DataFrame(
        {
            "factor": bridge_factor,
            "phase": bridge["rt_phase"].astype(str),
            "cycle_identity": "limited_realtime_bridge",
        },
        index=bridge.index,
    )
    return pd.concat([history, bridge_state]).sort_index()


def _phase_statistics(joined: pd.DataFrame) -> dict[str, dict[str, float | int]]:
    statistics: dict[str, dict[str, float | int]] = {}
    for phase in PHASES:
        values = joined.loc[joined["phase"] == phase, "return"].dropna()
        statistics[phase] = {
            "n": int(len(values)),
            "ann_return": float(values.mean() * 12.0) if len(values) else 0.0,
            "ann_vol": (
                float(values.std(ddof=1) * np.sqrt(12.0)) if len(values) > 1 else 0.0
            ),
            "positive_rate": float((values > 0).mean()) if len(values) else 0.0,
        }
    return statistics


def _oos_r2(frame: pd.DataFrame) -> tuple[float | None, int]:
    minimum_train = 96
    if len(frame) <= minimum_train:
        return None, 0
    predictions: list[float] = []
    baselines: list[float] = []
    actuals: list[float] = []
    folds = 0
    for start in range(minimum_train, len(frame), 12):
        train = frame.iloc[:start]
        test = frame.iloc[start : start + 12]
        if test.empty:
            continue
        means = train[["level", "slope3"]].mean()
        scales = train[["level", "slope3"]].std(ddof=0).replace(0.0, np.nan)
        train_features = (train[["level", "slope3"]] - means) / scales
        test_features = (test[["level", "slope3"]] - means) / scales
        if train_features.isna().any().any() or test_features.isna().any().any():
            continue
        model = sm.OLS(
            train["return"],
            sm.add_constant(train_features, has_constant="add"),
        ).fit()
        predictions.extend(
            model.predict(sm.add_constant(test_features, has_constant="add")).tolist()
        )
        baselines.extend([float(train["return"].mean())] * len(test))
        actuals.extend(test["return"].tolist())
        folds += 1
    if not actuals:
        return None, 0
    actual = np.asarray(actuals)
    prediction = np.asarray(predictions)
    baseline = np.asarray(baselines)
    denominator = float(np.square(actual - baseline).sum())
    if denominator <= 0:
        return None, folds
    return float(1.0 - np.square(actual - prediction).sum() / denominator), folds


def _regression_statistics(joined: pd.DataFrame) -> dict[str, object]:
    features = pd.DataFrame(
        {
            "return": joined["return"],
            "level": joined["factor"].shift(1),
            "slope3": joined["factor"].diff(3).shift(1),
        }
    ).dropna()
    if len(features) < 36:
        return {
            "beta_level": None,
            "beta_slope3": None,
            "beta_level_ci90": None,
            "beta_slope3_ci90": None,
            "p_level": None,
            "p_slope3": None,
            "impact_bps_per_1sigma": None,
            "in_sample_r2": None,
            "oos_r2": None,
            "oos_folds": 0,
            "actual_2019": None,
            "c4_assoc_contribution_2019": None,
        }
    means = features[["level", "slope3"]].mean()
    scales = features[["level", "slope3"]].std(ddof=0).replace(0.0, np.nan)
    standardized = (features[["level", "slope3"]] - means) / scales
    model = sm.OLS(
        features["return"],
        sm.add_constant(standardized, has_constant="add"),
    ).fit(cov_type="HAC", cov_kwds={"maxlags": 3})
    confidence = model.conf_int(alpha=0.10)
    coefficients = model.params[["level", "slope3"]]
    contribution = standardized.mul(coefficients, axis=1).sum(axis=1)
    returns_2019 = features.loc["2019", "return"] if 2019 in features.index.year else None
    contribution_2019 = contribution.loc["2019"] if 2019 in contribution.index.year else None
    oos_r2, oos_folds = _oos_r2(features)
    return {
        "beta_level": float(coefficients["level"]),
        "beta_slope3": float(coefficients["slope3"]),
        "beta_level_ci90": confidence.loc["level"].astype(float).tolist(),
        "beta_slope3_ci90": confidence.loc["slope3"].astype(float).tolist(),
        "p_level": float(model.pvalues["level"]),
        "p_slope3": float(model.pvalues["slope3"]),
        "impact_bps_per_1sigma": float(np.linalg.norm(coefficients) * 10_000.0),
        "in_sample_r2": float(model.rsquared),
        "oos_r2": oos_r2,
        "oos_folds": oos_folds,
        "actual_2019": (
            float((1.0 + returns_2019).prod() - 1.0)
            if returns_2019 is not None and len(returns_2019)
            else None
        ),
        "c4_assoc_contribution_2019": (
            float(contribution_2019.sum())
            if contribution_2019 is not None and len(contribution_2019)
            else None
        ),
    }


def _confidence(regression: dict[str, object]) -> str:
    oos_r2 = regression["oos_r2"]
    significant = any(
        value is not None and float(value) < 0.10
        for value in (regression["p_level"], regression["p_slope3"])
    )
    if oos_r2 is not None and float(oos_r2) > 0 and significant:
        return "high"
    if (oos_r2 is not None and float(oos_r2) > 0) or significant:
        return "medium"
    return "low"


def build_asset_statistics(
    returns: pd.DataFrame,
    c4_state: pd.DataFrame,
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for category, name in returns.columns:
        asset_return = pd.to_numeric(returns[(category, name)], errors="coerce")
        joined = pd.concat(
            [asset_return.rename("return"), c4_state],
            axis=1,
        ).dropna(subset=["return", "factor", "phase"])
        if joined.empty:
            continue
        phase_stats = _phase_statistics(joined)
        best_phase = max(PHASES, key=lambda phase: phase_stats[phase]["ann_return"])
        worst_phase = min(PHASES, key=lambda phase: phase_stats[phase]["ann_return"])
        regression = _regression_statistics(joined)
        rows.append(
            {
                "asset_id": f"{category}||{name}",
                "category": str(category),
                "name": str(name),
                "start": joined.index.min().strftime("%Y-%m"),
                "end": joined.index.max().strftime("%Y-%m"),
                "n_months": int(len(joined)),
                "data_identity": (
                    "direct_with_limited_cycle_bridge"
                    if "limited_realtime_bridge" in set(joined["cycle_identity"])
                    else "direct"
                ),
                "phase_stats": phase_stats,
                "best_phase": best_phase,
                "worst_phase": worst_phase,
                "recovery_minus_contraction": float(
                    phase_stats["recovery"]["ann_return"]
                    - phase_stats["contraction"]["ann_return"]
                ),
                **regression,
                "confidence": _confidence(regression),
            }
        )
    confidence_counts = pd.Series(
        [row["confidence"] for row in rows], dtype="object"
    ).value_counts()
    return {
        "meta": {
            "generated": date.today().isoformat(),
            "cycle": "C4 inventory cycle",
            "cycle_source": "retrospective C4 factor plus explicitly limited realtime bridge",
            "return_source": "output/monthly_returns_20y.parquet",
            "attribution_label": "C4 explainable association contribution; not causal attribution",
            "features": "one-month lagged standardized C4 level and three-month slope",
            "inference": "OLS with HAC(3) 90% intervals",
            "validation": "expanding 12-month block out-of-sample R2",
            "missing_rule": "no synthetic return history is created",
        },
        "summary": {
            "total_rows": len(rows),
            "observed_assets": len(rows),
            "unavailable_assets": 0,
            "categories": sorted({row["category"] for row in rows}),
            "positive_oos_r2": sum(
                row["oos_r2"] is not None and float(row["oos_r2"]) > 0
                for row in rows
            ),
            "high_confidence": int(confidence_counts.get("high", 0)),
            "medium_confidence": int(confidence_counts.get("medium", 0)),
            "low_confidence": int(confidence_counts.get("low", 0)),
        },
        "assets": rows,
        "phase_labels": {
            "recovery": "复苏",
            "expansion": "扩张",
            "downturn": "放缓",
            "contraction": "收缩",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    historical = json.loads(HISTORICAL_PATH.read_text(encoding="utf-8"))
    realtime = json.loads(REALTIME_PATH.read_text(encoding="utf-8"))
    payload = build_asset_statistics(returns, build_c4_state(historical, realtime))
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
