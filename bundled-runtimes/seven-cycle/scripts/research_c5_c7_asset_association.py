"""Build non-causal C5/C7 asset association research mappings.

The output describes historical return and risk distributions across state
quadrants plus lagged-state statistical associations. It does not publish
asset forecasts, causal attribution, portfolio weights, or trading signals.
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts.refresh_c4_asset_statistics import (
        _confidence,
        _phase_statistics,
        _regression_statistics,
    )
except ModuleNotFoundError:
    from refresh_c4_asset_statistics import (
        _confidence,
        _phase_statistics,
        _regression_statistics,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETURNS_PATH = PROJECT_ROOT / "output" / "monthly_returns_20y.parquet"
STATE_PATHS = {
    "C5": PROJECT_ROOT / "output" / "c5_liquidity_state_research.json",
    "C7": PROJECT_ROOT / "output" / "c7_risk_appetite_state_research.json",
}
OUTPUT_PATH = PROJECT_ROOT / "output" / "c5_c7_asset_association.json"
PHASES = ("recovery", "expansion", "slowdown", "contraction")
MIN_MONTHS = 60
MIN_QUADRANT_MONTHS = 6


def _state_phase(level: float, slope: float) -> str | None:
    if not np.isfinite(level) or not np.isfinite(slope):
        return None
    if level < 0.0 and slope >= 0.0:
        return "recovery"
    if level >= 0.0 and slope >= 0.0:
        return "expansion"
    if level >= 0.0 and slope < 0.0:
        return "slowdown"
    return "contraction"


def build_state_frame(payload: dict[str, object]) -> pd.DataFrame:
    timeline = pd.DataFrame(payload["timeline"])
    index = pd.PeriodIndex(timeline["date"], freq="M").to_timestamp("M")
    factor = pd.Series(
        pd.to_numeric(timeline["state"], errors="coerce").to_numpy(),
        index=index,
    )
    slope = (
        pd.Series(
            pd.to_numeric(timeline["slope3"], errors="coerce").to_numpy(),
            index=index,
        )
        if "slope3" in timeline
        else factor.diff(3) / 3.0
    )
    return pd.DataFrame(
        {
            "factor": factor,
            "phase": [
                _state_phase(float(level), float(change))
                for level, change in zip(factor, slope, strict=True)
            ],
            "cycle_identity": "latest_restated_state_not_true_vintage",
        },
        index=index,
    )


def _phase_payload(statistics: dict[str, dict[str, float | int]]) -> dict[str, object]:
    return {
        phase: {
            "n": int(statistics[source]["n"]),
            "annReturn": float(statistics[source]["ann_return"]),
            "annVol": float(statistics[source]["ann_vol"]),
            "positiveRate": float(statistics[source]["positive_rate"]),
        }
        for phase, source in (
            ("recovery", "recovery"),
            ("expansion", "expansion"),
            ("slowdown", "downturn"),
            ("contraction", "contraction"),
        )
    }


def build_cycle_mapping(
    cycle_id: str,
    returns: pd.DataFrame,
    state_payload: dict[str, object],
) -> dict[str, object]:
    state = build_state_frame(state_payload)
    assets: list[dict[str, object]] = []
    for category, name in returns.columns:
        asset_return = pd.to_numeric(returns[(category, name)], errors="coerce")
        joined = pd.concat(
            [asset_return.rename("return"), state],
            axis=1,
        ).dropna(subset=["return", "factor", "phase"])
        if joined.empty:
            continue
        raw_phase_statistics = _phase_statistics(
            joined.assign(
                phase=joined["phase"].replace({"slowdown": "downturn"})
            )
        )
        phase_statistics = _phase_payload(raw_phase_statistics)
        regression = _regression_statistics(joined)
        phase_returns = {
            phase: float(phase_statistics[phase]["annReturn"])
            for phase in PHASES
        }
        best_phase = max(PHASES, key=phase_returns.get)
        worst_phase = min(PHASES, key=phase_returns.get)
        p_values = [
            float(value)
            for value in (regression["p_level"], regression["p_slope3"])
            if value is not None
        ]
        eligible = bool(
            len(joined) >= MIN_MONTHS
            and min(
                int(phase_statistics[phase]["n"])
                for phase in PHASES
            )
            >= MIN_QUADRANT_MONTHS
        )
        assets.append(
            {
                "assetId": f"{category}::{name}",
                "category": str(category),
                "name": str(name),
                "eligible": eligible,
                "startPeriod": joined.index.min().strftime("%Y-%m"),
                "endPeriod": joined.index.max().strftime("%Y-%m"),
                "observations": int(len(joined)),
                "dataIdentity": "direct_asset_return_with_restated_state",
                "source": "output/monthly_returns_20y.parquet",
                "phaseStats": phase_statistics,
                "bestPhase": best_phase,
                "worstPhase": worst_phase,
                "phaseSpread": phase_returns[best_phase] - phase_returns[worst_phase],
                "betaLevel": regression["beta_level"],
                "betaSlope3": regression["beta_slope3"],
                "impactBpsPer1Sigma": regression["impact_bps_per_1sigma"],
                "oosR2": regression["oos_r2"],
                "hacPValue": min(p_values) if p_values else None,
                "confidence": _confidence(regression),
                "associationQualified": bool(
                    regression["oos_r2"] is not None
                    and float(regression["oos_r2"]) > 0.0
                    and p_values
                    and min(p_values) < 0.10
                ),
            }
        )
    eligible_assets = [asset for asset in assets if asset["eligible"]]
    positive_oos = sum(
        asset["oosR2"] is not None and float(asset["oosR2"]) > 0.0
        for asset in eligible_assets
    )
    qualified_associations = sum(
        bool(asset["associationQualified"]) for asset in eligible_assets
    )
    validation_source = (
        state_payload.get("pathValidation", {})
        if cycle_id == "C7"
        else state_payload.get("validation", {})
    )
    qualified_horizons = [
        horizon
        for horizon, validation in validation_source.items()
        if validation.get("qualified")
    ]
    labels = (
        {
            "recovery": "流动性修复",
            "expansion": "流动性扩张",
            "slowdown": "流动性降温",
            "contraction": "流动性收紧",
        }
        if cycle_id == "C5"
        else {
            "recovery": "风险偏好修复",
            "expansion": "风险偏好扩张",
            "slowdown": "风险偏好降温",
            "contraction": "风险偏好收缩",
        }
    )
    return {
        "kind": "state_association",
        "cycleId": cycle_id,
        "title": f"{cycle_id} 状态—资产历史统计关联",
        "status": "research_association_only",
        "summary": {
            "eligibleAssets": len(eligible_assets),
            "positiveOosR2": int(positive_oos),
            "qualifiedAssociations": int(qualified_associations),
            "categories": sorted({asset["category"] for asset in eligible_assets}),
        },
        "phaseLabels": labels,
        "currentState": {
            **state_payload["current"],
            "qualifiedDirectionHorizons": qualified_horizons,
            "assetForecastStatus": state_payload["governance"]["assetForecastStatus"],
        },
        "assetValidation": state_payload["assetValidation"],
        "assets": assets,
        "display": {
            "sampleLabel": "月度样本",
            "observationUnit": "个月",
            "returnLabel": "月度收益年化",
            "volatilityLabel": "月度波动年化",
            "sectionTitle": "状态分区下的资产收益—风险表现",
            "description": "按状态水平与三个月斜率划分四个统计象限；仅描述历史关联，不代表独立周期相位。",
        },
        "caveat": (
            "状态关联使用修订后序列并滞后一个月进入回归；"
            "不是因果归因，不可加总为七周期贡献，也不解锁资产方向预测。"
        ),
    }


def build_payload() -> dict[str, object]:
    returns = pd.read_parquet(RETURNS_PATH)
    returns.index = pd.to_datetime(returns.index)
    cycles = {
        cycle_id: build_cycle_mapping(
            cycle_id,
            returns,
            json.loads(path.read_text(encoding="utf-8")),
        )
        for cycle_id, path in STATE_PATHS.items()
    }
    return {
        "meta": {
            "generated": date.today().isoformat(),
            "dataIdentity": "latest_restated_state_not_true_vintage",
            "notCausalAttribution": True,
            "notAssetForecast": True,
            "notPortfolioBacktest": True,
        },
        "cycles": cycles,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                cycle_id: mapping["summary"]
                for cycle_id, mapping in payload["cycles"].items()
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
