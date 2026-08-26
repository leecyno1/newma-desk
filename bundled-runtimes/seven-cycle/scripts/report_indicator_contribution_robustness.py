#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MARKET_DATA = ROOT / "web" / "public" / "data" / "market-surface.json"
DETAIL_OUTPUT = ROOT / "output" / "indicator_cycle_contribution_filter_robustness.csv"
SUMMARY_OUTPUT = ROOT / "output" / "indicator_cycle_contribution_filter_robustness_summary.csv"
REPORT_OUTPUT = ROOT / "output" / "indicator_cycle_contribution_filter_robustness_report.md"


def _rate(value: float) -> str:
    if not np.isfinite(value):
        return "—"
    return f"{value * 100:.1f}%"


def _number(value: float) -> str:
    return "—" if not np.isfinite(value) else f"{value:.3f}"


def _gain_calibration_text(cycle_id: str, calibration: dict[str, object]) -> str:
    status = {
        "adopted": "采用",
        "rejected": "拒绝",
        "unavailable": "不可用",
    }.get(str(calibration.get("status")), str(calibration.get("status")))
    if calibration.get("gain") is None:
        return f"{cycle_id}：{status}（{calibration.get('reason', '样本不足')}）"
    return (
        f"{cycle_id}：{status}，训练增益{_number(float(calibration['gain']))}，"
        f"验证段误差改善{_rate(float(calibration['validationRelativeImprovement']))}，"
        f"审计段改善{_rate(float(calibration['auditRelativeImprovement']))}，"
        f"改善轨道占比分别为"
        f"{_rate(float(calibration['validationImprovedTrackShare']))}/"
        f"{_rate(float(calibration['auditImprovedTrackShare']))}"
    )


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "|" + "|".join("---:" for _ in columns) + "|"
    rows = [
        "| " + " | ".join(str(row[column]) for column in columns) + " |"
        for _, row in frame.iterrows()
    ]
    return "\n".join([header, divider, *rows])


def build_report() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    payload = json.loads(MARKET_DATA.read_text(encoding="utf-8"))
    rows: list[dict[str, object]] = []
    for track in payload["tracks"]:
        study = track.get("cycleContribution", {})
        if study.get("status") != "retrospective_diagnostic":
            continue
        overall = study.get("filterRobustness", {})
        thresholds = overall.get("thresholds", {})
        realtime = study.get("realtimeConfirmation", {})
        for cycle_id, component in study["current"]["components"].items():
            robustness = component.get("filterRobustness", {})
            realtime_component = (
                realtime.get("current", {}).get("components", {}).get(cycle_id, {})
                if realtime.get("status") == "causal_realtime_confirmation"
                else {}
            )
            path_correlation = robustness.get("pathCorrelation")
            point_difference = robustness.get("relativePointDifference")
            share_difference = robustness.get("absoluteShareDifference")
            variance_difference = robustness.get("varianceShareDifference")
            rows.append(
                {
                    "cycle_id": cycle_id,
                    "track_id": track["id"],
                    "label": track["label"],
                    "category": track["category"],
                    "group": track["group"],
                    "stable": robustness.get("status") == "stable",
                    "primary_model_pass": overall.get("primaryModelQuality") == "stable",
                    "comparison_model_pass": overall.get("comparisonModelQuality") == "stable",
                    "direction_pass": robustness.get("directionAgreement") is True,
                    "path_pass": (
                        path_correlation is not None
                        and path_correlation >= thresholds.get("minimumPathCorrelation", 0.70)
                    ),
                    "point_amplitude_pass": (
                        point_difference is not None
                        and point_difference
                        <= thresholds.get("maximumRelativePointDifference", 0.75)
                    ),
                    "share_pass": (
                        share_difference is not None
                        and share_difference
                        <= thresholds.get("maximumAbsoluteShareDifference", 0.15)
                    ),
                    "variance_pass": (
                        variance_difference is not None
                        and variance_difference
                        <= thresholds.get("maximumVarianceShareDifference", 0.15)
                    ),
                    "path_correlation": path_correlation,
                    "relative_point_difference": point_difference,
                    "absolute_share_difference": share_difference,
                    "variance_share_difference": variance_difference,
                    "point_contribution": component["pointContribution"],
                    "absolute_share": component["absoluteShare"],
                    "variance_share_120": component["varianceShare120"],
                    "realtime_eligible": bool(realtime_component),
                    "realtime_confirmed": (
                        realtime_component.get("status") == "limited_confirmed"
                    ),
                    "realtime_state_weight_model": realtime_component.get(
                        "stateWeightModel"
                    ),
                    "realtime_peer_shared_family_level": realtime_component.get(
                        "peerSharedFamilyLevel"
                    ),
                    "realtime_peer_shared_peer_count": realtime_component.get(
                        "peerSharedPeerCount"
                    ),
                    "realtime_orthogonalization_uncertainty_share": (
                        realtime_component.get(
                            "orthogonalizationUncertaintyShare"
                        )
                    ),
                    "realtime_orthogonalization_span_uncertainty_share": (
                        realtime_component.get(
                            "orthogonalizationSpanUncertaintyShare"
                        )
                    ),
                    "realtime_signal_to_uncertainty": realtime_component.get(
                        "signalToUncertainty"
                    ),
                    "realtime_coefficient_sign_agreement": realtime_component.get(
                        "coefficientSignAgreement"
                    ),
                    "realtime_coefficient_uncertainty_share": realtime_component.get(
                        "coefficientUncertaintyShare"
                    ),
                    "realtime_state_specification_direction_agreement": (
                        realtime_component.get(
                            "stateSpecificationDirectionAgreement"
                        )
                    ),
                    "realtime_rolling_state_specification_direction_agreement": (
                        realtime_component.get(
                            "rollingStateSpecificationDirectionAgreement"
                        )
                    ),
                    "realtime_state_specification_uncertainty_share": (
                        realtime_component.get(
                            "stateSpecificationUncertaintyShare"
                        )
                    ),
                    "realtime_responsive_weight": realtime_component.get(
                        "stateSpecificationWeights", {}
                    ).get("responsive"),
                    "realtime_baseline_weight": realtime_component.get(
                        "stateSpecificationWeights", {}
                    ).get("baseline"),
                    "realtime_smooth_weight": realtime_component.get(
                        "stateSpecificationWeights", {}
                    ).get("smooth"),
                    "realtime_state_specification_effective_count": (
                        realtime_component.get(
                            "stateSpecificationEffectiveCount"
                        )
                    ),
                    "realtime_rolling_direction_agreement": realtime_component.get(
                        "rollingDirectionAgreement"
                    ),
                    "realtime_rolling_correlation": realtime_component.get(
                        "rollingContributionCorrelation"
                    ),
                    "realtime_median_absolute_revision": realtime_component.get(
                        "medianAbsoluteRevision"
                    ),
                    "realtime_rolling_reconstruction_r2": realtime.get(
                        "training", {}
                    ).get(
                        "rollingReconstructionR2"
                    ),
                    "realtime_equal_median_rolling_reconstruction_r2": realtime.get(
                        "training", {}
                    ).get(
                        "equalMedianRollingReconstructionR2"
                    ),
                    "realtime_dynamic_weight_r2_improvement": realtime.get(
                        "training", {}
                    ).get(
                        "rollingR2ImprovementVsEqualMedian"
                    ),
                    "realtime_peer_shared_status": realtime.get(
                        "training", {}
                    ).get("peerSharedStatus"),
                    "realtime_peer_shared_r2_improvement": realtime.get(
                        "training", {}
                    ).get("peerSharedRollingR2Improvement"),
                    "realtime_peer_shared_mae_improvement": realtime.get(
                        "training", {}
                    ).get("peerSharedMaeImprovement"),
                    "realtime_peer_shared_direction_improvement": realtime.get(
                        "training", {}
                    ).get("peerSharedDirectionImprovement"),
                    "realtime_dynamic_factor_status": realtime.get(
                        "training", {}
                    ).get("dynamicFactorStatus"),
                    "realtime_dynamic_factor_r2_improvement": realtime.get(
                        "training", {}
                    ).get("dynamicFactorRollingR2Improvement"),
                    "realtime_dynamic_factor_mae_improvement": realtime.get(
                        "training", {}
                    ).get("dynamicFactorMaeImprovement"),
                    "realtime_dynamic_factor_direction_improvement": realtime.get(
                        "training", {}
                    ).get("dynamicFactorDirectionImprovement"),
                    "realtime_nearest_factor_status": realtime.get(
                        "training", {}
                    ).get("nearestFactorStatus"),
                    "realtime_nearest_factor_r2_improvement": realtime.get(
                        "training", {}
                    ).get("nearestFactorRollingR2Improvement"),
                    "realtime_nearest_factor_mae_improvement": realtime.get(
                        "training", {}
                    ).get("nearestFactorMaeImprovement"),
                    "realtime_nearest_factor_direction_improvement": realtime.get(
                        "training", {}
                    ).get("nearestFactorDirectionImprovement"),
                    "realtime_nearest_factor_specification_stable": realtime.get(
                        "training", {}
                    ).get("nearestFactorSpecificationStable"),
                    "realtime_nearest_factor_robustly_adopted": realtime.get(
                        "training", {}
                    ).get("nearestFactorRobustlyAdopted"),
                    "realtime_nearest_factor_early_vintage_r2_improvement": realtime.get(
                        "training", {}
                    ).get("nearestFactorVintageSplits", {}).get(
                        "early", {}
                    ).get("r2Improvement"),
                    "realtime_nearest_factor_late_vintage_r2_improvement": realtime.get(
                        "training", {}
                    ).get("nearestFactorVintageSplits", {}).get(
                        "late", {}
                    ).get("r2Improvement"),
                    "realtime_low_target_variance_warning": realtime.get(
                        "training", {}
                    ).get("lowTargetVarianceWarning"),
                    "realtime_causal_orthogonal_status": realtime.get(
                        "training", {}
                    ).get("causalOrthogonalStatus"),
                    "realtime_orthogonal_primary_r2_improvement": realtime.get(
                        "training", {}
                    ).get("orthogonalPrimaryRollingR2Improvement"),
                    "realtime_orthogonal_comparison_r2_improvement": realtime.get(
                        "training", {}
                    ).get("orthogonalComparisonRollingR2Improvement"),
                    "realtime_base_maximum_correlation": realtime.get(
                        "training", {}
                    ).get("baseComponentCollinearity", {}).get(
                        "maximumAbsoluteCorrelation"
                    ),
                    "realtime_orthogonal_maximum_correlation": realtime.get(
                        "training", {}
                    ).get("orthogonalPrimaryComponentCollinearity", {}).get(
                        "maximumAbsoluteCorrelation"
                    ),
                    "realtime_base_condition_number": realtime.get(
                        "training", {}
                    ).get("baseComponentCollinearity", {}).get(
                        "conditionNumber"
                    ),
                    "realtime_orthogonal_condition_number": realtime.get(
                        "training", {}
                    ).get("orthogonalPrimaryComponentCollinearity", {}).get(
                        "conditionNumber"
                    ),
                    "realtime_endpoint_direction_agreement": realtime_component.get(
                        "endpointDirectionAgreement"
                    ),
                }
            )
    detail = pd.DataFrame(rows)
    summary_rows = []
    for cycle_id, frame in detail.groupby("cycle_id", sort=True):
        realtime_frame = frame.loc[frame["realtime_eligible"]]
        nearest_comparable = realtime_frame.loc[
            ~realtime_frame[
                "realtime_low_target_variance_warning"
            ].eq(True)
        ]
        orthogonal_frame = realtime_frame.loc[
            realtime_frame["realtime_causal_orthogonal_status"].eq("adopted")
        ]
        summary_rows.append(
            {
                "cycle_id": cycle_id,
                "eligible_tracks": len(frame),
                "stable_tracks": int(frame["stable"].sum()),
                "stable_rate": float(frame["stable"].mean()),
                "primary_model_pass_rate": float(frame["primary_model_pass"].mean()),
                "comparison_model_pass_rate": float(frame["comparison_model_pass"].mean()),
                "direction_pass_rate": float(frame["direction_pass"].mean()),
                "path_pass_rate": float(frame["path_pass"].mean()),
                "point_amplitude_pass_rate": float(frame["point_amplitude_pass"].mean()),
                "share_pass_rate": float(frame["share_pass"].mean()),
                "variance_pass_rate": float(frame["variance_pass"].mean()),
                "median_path_correlation": float(frame["path_correlation"].median()),
                "median_relative_point_difference": float(
                    frame["relative_point_difference"].median()
                ),
                "realtime_eligible_tracks": len(realtime_frame),
                "realtime_confirmed_tracks": int(
                    realtime_frame["realtime_confirmed"].sum()
                ),
                "realtime_confirmed_rate": (
                    float(realtime_frame["realtime_confirmed"].mean())
                    if not realtime_frame.empty
                    else np.nan
                ),
                "median_realtime_signal_to_uncertainty": float(
                    realtime_frame["realtime_signal_to_uncertainty"].median()
                ),
                "median_realtime_coefficient_sign_agreement": float(
                    realtime_frame["realtime_coefficient_sign_agreement"].median()
                ),
                "median_realtime_coefficient_uncertainty_share": float(
                    realtime_frame["realtime_coefficient_uncertainty_share"].median()
                ),
                "median_realtime_state_specification_direction_agreement": float(
                    realtime_frame[
                        "realtime_state_specification_direction_agreement"
                    ].median()
                ),
                "median_realtime_rolling_state_specification_direction_agreement": float(
                    realtime_frame[
                        "realtime_rolling_state_specification_direction_agreement"
                    ].median()
                ),
                "median_realtime_state_specification_uncertainty_share": float(
                    realtime_frame[
                        "realtime_state_specification_uncertainty_share"
                    ].median()
                ),
                "median_realtime_responsive_weight": float(
                    realtime_frame["realtime_responsive_weight"].median()
                ),
                "median_realtime_baseline_weight": float(
                    realtime_frame["realtime_baseline_weight"].median()
                ),
                "median_realtime_smooth_weight": float(
                    realtime_frame["realtime_smooth_weight"].median()
                ),
                "median_realtime_state_specification_effective_count": float(
                    realtime_frame[
                        "realtime_state_specification_effective_count"
                    ].median()
                ),
                "median_realtime_rolling_direction_agreement": float(
                    realtime_frame["realtime_rolling_direction_agreement"].median()
                ),
                "median_realtime_rolling_correlation": float(
                    realtime_frame["realtime_rolling_correlation"].median()
                ),
                "median_realtime_absolute_revision": float(
                    realtime_frame["realtime_median_absolute_revision"].median()
                ),
                "median_realtime_rolling_reconstruction_r2": float(
                    realtime_frame["realtime_rolling_reconstruction_r2"].median()
                ),
                "median_realtime_equal_median_rolling_reconstruction_r2": float(
                    realtime_frame[
                        "realtime_equal_median_rolling_reconstruction_r2"
                    ].median()
                ),
                "median_realtime_dynamic_weight_r2_improvement": float(
                    realtime_frame[
                        "realtime_dynamic_weight_r2_improvement"
                    ].median()
                ),
                "realtime_dynamic_weight_improved_tracks": int(
                    (
                        realtime_frame[
                            "realtime_dynamic_weight_r2_improvement"
                        ]
                        > 0.0
                    ).sum()
                ),
                "realtime_peer_shared_eligible_tracks": int(
                    realtime_frame["realtime_peer_shared_status"]
                    .isin(["adopted", "rejected"])
                    .sum()
                ),
                "realtime_peer_shared_adopted_tracks": int(
                    (
                        realtime_frame["realtime_peer_shared_status"]
                        == "adopted"
                    ).sum()
                ),
                "realtime_peer_shared_positive_r2_tracks": int(
                    (
                        realtime_frame[
                            "realtime_peer_shared_r2_improvement"
                        ]
                        > 0.0
                    ).sum()
                ),
                "median_realtime_peer_shared_r2_improvement": float(
                    realtime_frame[
                        "realtime_peer_shared_r2_improvement"
                    ].median()
                ),
                "median_realtime_peer_shared_mae_improvement": float(
                    realtime_frame[
                        "realtime_peer_shared_mae_improvement"
                    ].median()
                ),
                "median_realtime_peer_shared_direction_improvement": float(
                    realtime_frame[
                        "realtime_peer_shared_direction_improvement"
                    ].median()
                ),
                "realtime_dynamic_factor_eligible_tracks": int(
                    realtime_frame["realtime_dynamic_factor_status"]
                    .isin(["adopted", "rejected"])
                    .sum()
                ),
                "realtime_dynamic_factor_adopted_tracks": int(
                    realtime_frame["realtime_dynamic_factor_status"]
                    .eq("adopted")
                    .sum()
                ),
                "realtime_dynamic_factor_positive_r2_tracks": int(
                    (
                        realtime_frame[
                            "realtime_dynamic_factor_r2_improvement"
                        ]
                        > 0.0
                    ).sum()
                ),
                "median_realtime_dynamic_factor_r2_improvement": float(
                    realtime_frame[
                        "realtime_dynamic_factor_r2_improvement"
                    ].median()
                ),
                "median_realtime_dynamic_factor_mae_improvement": float(
                    realtime_frame[
                        "realtime_dynamic_factor_mae_improvement"
                    ].median()
                ),
                "median_realtime_dynamic_factor_direction_improvement": float(
                    realtime_frame[
                        "realtime_dynamic_factor_direction_improvement"
                    ].median()
                ),
                "realtime_nearest_factor_eligible_tracks": int(
                    nearest_comparable["realtime_nearest_factor_status"]
                    .isin(["adopted", "rejected"])
                    .sum()
                ),
                "realtime_nearest_factor_adopted_tracks": int(
                    realtime_frame["realtime_nearest_factor_status"]
                    .eq("adopted")
                    .sum()
                ),
                "realtime_nearest_factor_positive_r2_tracks": int(
                    (
                        nearest_comparable[
                            "realtime_nearest_factor_r2_improvement"
                        ]
                        > 0.0
                    ).sum()
                ),
                "median_realtime_nearest_factor_r2_improvement": float(
                    nearest_comparable[
                        "realtime_nearest_factor_r2_improvement"
                    ].median()
                ),
                "median_realtime_nearest_factor_mae_improvement": float(
                    nearest_comparable[
                        "realtime_nearest_factor_mae_improvement"
                    ].median()
                ),
                "median_realtime_nearest_factor_direction_improvement": float(
                    nearest_comparable[
                        "realtime_nearest_factor_direction_improvement"
                    ].median()
                ),
                "realtime_nearest_factor_specification_stable_tracks": int(
                    nearest_comparable[
                        "realtime_nearest_factor_specification_stable"
                    ].eq(True).sum()
                ),
                "realtime_nearest_factor_robustly_adopted_tracks": int(
                    realtime_frame[
                        "realtime_nearest_factor_robustly_adopted"
                    ].eq(True).sum()
                ),
                "realtime_nearest_factor_positive_early_vintage_tracks": int(
                    (
                        nearest_comparable[
                            "realtime_nearest_factor_early_vintage_r2_improvement"
                        ] > 0.0
                    ).sum()
                ),
                "realtime_nearest_factor_positive_late_vintage_tracks": int(
                    (
                        nearest_comparable[
                            "realtime_nearest_factor_late_vintage_r2_improvement"
                        ] > 0.0
                    ).sum()
                ),
                "median_realtime_nearest_factor_early_vintage_r2_improvement": float(
                    nearest_comparable[
                        "realtime_nearest_factor_early_vintage_r2_improvement"
                    ].median()
                ),
                "median_realtime_nearest_factor_late_vintage_r2_improvement": float(
                    nearest_comparable[
                        "realtime_nearest_factor_late_vintage_r2_improvement"
                    ].median()
                ),
                "realtime_low_target_variance_warning_tracks": int(
                    realtime_frame[
                        "realtime_low_target_variance_warning"
                    ].eq(True).sum()
                ),
                "realtime_causal_orthogonal_adopted_tracks": int(
                    (
                        realtime_frame[
                            "realtime_causal_orthogonal_status"
                        ]
                        == "adopted"
                    ).sum()
                ),
                "realtime_causal_orthogonal_positive_r2_tracks": int(
                    (
                        realtime_frame[
                            "realtime_orthogonal_primary_r2_improvement"
                        ]
                        > 0.0
                    ).sum()
                ),
                "median_realtime_orthogonal_primary_r2_improvement": float(
                    realtime_frame[
                        "realtime_orthogonal_primary_r2_improvement"
                    ].median()
                ),
                "median_realtime_orthogonal_comparison_r2_improvement": float(
                    realtime_frame[
                        "realtime_orthogonal_comparison_r2_improvement"
                    ].median()
                ),
                "median_realtime_base_maximum_correlation": float(
                    realtime_frame[
                        "realtime_base_maximum_correlation"
                    ].median()
                ),
                "median_realtime_orthogonal_maximum_correlation": float(
                    realtime_frame[
                        "realtime_orthogonal_maximum_correlation"
                    ].median()
                ),
                "median_realtime_base_condition_number": float(
                    realtime_frame[
                        "realtime_base_condition_number"
                    ].median()
                ),
                "median_realtime_orthogonal_condition_number": float(
                    realtime_frame[
                        "realtime_orthogonal_condition_number"
                    ].median()
                ),
                "median_realtime_orthogonalization_uncertainty_share": float(
                    orthogonal_frame[
                        "realtime_orthogonalization_uncertainty_share"
                    ].median()
                ),
                "median_realtime_orthogonalization_span_uncertainty_share": float(
                    orthogonal_frame[
                        "realtime_orthogonalization_span_uncertainty_share"
                    ].median()
                ),
            }
        )
    summary = pd.DataFrame(summary_rows)
    display = summary.copy()
    rate_columns = [
        "stable_rate",
        "primary_model_pass_rate",
        "comparison_model_pass_rate",
        "direction_pass_rate",
        "path_pass_rate",
        "point_amplitude_pass_rate",
        "share_pass_rate",
        "variance_pass_rate",
        "realtime_confirmed_rate",
    ]
    for column in rate_columns:
        display[column] = display[column].map(_rate)
    display["median_path_correlation"] = display["median_path_correlation"].map(_number)
    display["median_relative_point_difference"] = display[
        "median_relative_point_difference"
    ].map(_number)
    display["median_realtime_signal_to_uncertainty"] = display[
        "median_realtime_signal_to_uncertainty"
    ].map(_number)
    display["median_realtime_coefficient_sign_agreement"] = display[
        "median_realtime_coefficient_sign_agreement"
    ].map(_rate)
    display["median_realtime_coefficient_uncertainty_share"] = display[
        "median_realtime_coefficient_uncertainty_share"
    ].map(_rate)
    display["median_realtime_state_specification_direction_agreement"] = display[
        "median_realtime_state_specification_direction_agreement"
    ].map(_rate)
    display[
        "median_realtime_rolling_state_specification_direction_agreement"
    ] = display[
        "median_realtime_rolling_state_specification_direction_agreement"
    ].map(_rate)
    display["median_realtime_state_specification_uncertainty_share"] = display[
        "median_realtime_state_specification_uncertainty_share"
    ].map(_rate)
    for column in (
        "median_realtime_responsive_weight",
        "median_realtime_baseline_weight",
        "median_realtime_smooth_weight",
    ):
        display[column] = display[column].map(_rate)
    display["median_realtime_state_specification_effective_count"] = display[
        "median_realtime_state_specification_effective_count"
    ].map(_number)
    display["median_realtime_rolling_direction_agreement"] = display[
        "median_realtime_rolling_direction_agreement"
    ].map(_rate)
    display["median_realtime_rolling_correlation"] = display[
        "median_realtime_rolling_correlation"
    ].map(_number)
    display["median_realtime_absolute_revision"] = display[
        "median_realtime_absolute_revision"
    ].map(_number)
    display["median_realtime_rolling_reconstruction_r2"] = display[
        "median_realtime_rolling_reconstruction_r2"
    ].map(_rate)
    display["median_realtime_equal_median_rolling_reconstruction_r2"] = display[
        "median_realtime_equal_median_rolling_reconstruction_r2"
    ].map(_rate)
    display["median_realtime_dynamic_weight_r2_improvement"] = display[
        "median_realtime_dynamic_weight_r2_improvement"
    ].map(_rate)
    display["median_realtime_peer_shared_r2_improvement"] = display[
        "median_realtime_peer_shared_r2_improvement"
    ].map(_rate)
    display["median_realtime_peer_shared_mae_improvement"] = display[
        "median_realtime_peer_shared_mae_improvement"
    ].map(_number)
    display["median_realtime_peer_shared_direction_improvement"] = display[
        "median_realtime_peer_shared_direction_improvement"
    ].map(_rate)
    display["median_realtime_dynamic_factor_r2_improvement"] = display[
        "median_realtime_dynamic_factor_r2_improvement"
    ].map(_rate)
    display["median_realtime_dynamic_factor_mae_improvement"] = display[
        "median_realtime_dynamic_factor_mae_improvement"
    ].map(_number)
    display["median_realtime_dynamic_factor_direction_improvement"] = display[
        "median_realtime_dynamic_factor_direction_improvement"
    ].map(_rate)
    display["median_realtime_nearest_factor_r2_improvement"] = display[
        "median_realtime_nearest_factor_r2_improvement"
    ].map(_rate)
    display["median_realtime_nearest_factor_mae_improvement"] = display[
        "median_realtime_nearest_factor_mae_improvement"
    ].map(_number)
    display["median_realtime_nearest_factor_direction_improvement"] = display[
        "median_realtime_nearest_factor_direction_improvement"
    ].map(_rate)
    for column in (
        "median_realtime_orthogonal_primary_r2_improvement",
        "median_realtime_orthogonal_comparison_r2_improvement",
        "median_realtime_orthogonalization_uncertainty_share",
        "median_realtime_orthogonalization_span_uncertainty_share",
    ):
        display[column] = display[column].map(_rate)
    for column in (
        "median_realtime_base_maximum_correlation",
        "median_realtime_orthogonal_maximum_correlation",
        "median_realtime_base_condition_number",
        "median_realtime_orthogonal_condition_number",
    ):
        display[column] = display[column].map(_number)
    annual = payload["indicatorContributionStudy"]["longHistory"]["cycles"]
    annual_rows = []
    for cycle_id in ("C1", "C2", "C3"):
        cycle = annual[cycle_id]
        annual_rows.append(
            {
                "周期": cycle_id,
                "可用指标": cycle.get("eligibleTracks", 0),
                "历史路径通过": cycle.get("pathStableTracks", 0),
                "模型质量通过": cycle.get("modelStableTracks", 0),
                "严格稳定": cycle.get("stableTracks", 0),
                "方向一致": cycle.get("directionAgreementTracks", 0),
                "点幅度通过": cycle.get("pointAmplitudeStableTracks", 0),
                "周期占比通过": cycle.get("absoluteShareStableTracks", 0),
                "解释方差通过": cycle.get("varianceShareStableTracks", 0),
                "路径相关中位": _number(cycle.get("medianFilterPathCorrelation", np.nan)),
            }
        )
    annual_display = pd.DataFrame(annual_rows)
    coefficient_uncertainty = summary[
        "median_realtime_coefficient_uncertainty_share"
    ].dropna()
    state_specification_uncertainty = summary[
        "median_realtime_state_specification_uncertainty_share"
    ].dropna()
    coefficient_uncertainty_range = (
        f"{_rate(float(coefficient_uncertainty.min()))}—"
        f"{_rate(float(coefficient_uncertainty.max()))}"
    )
    state_specification_uncertainty_range = (
        f"{_rate(float(state_specification_uncertainty.min()))}—"
        f"{_rate(float(state_specification_uncertainty.max()))}"
    )
    dynamic_improvement_rate = (
        summary["realtime_dynamic_weight_improved_tracks"]
        / summary["realtime_eligible_tracks"]
    )
    dynamic_improvement_rate_range = (
        f"{_rate(float(dynamic_improvement_rate.min()))}—"
        f"{_rate(float(dynamic_improvement_rate.max()))}"
    )
    dynamic_r2_improvement = summary[
        "median_realtime_dynamic_weight_r2_improvement"
    ].dropna()
    dynamic_r2_improvement_range = (
        f"{_rate(float(dynamic_r2_improvement.min()))}—"
        f"{_rate(float(dynamic_r2_improvement.max()))}"
    )
    effective_specification_count = summary[
        "median_realtime_state_specification_effective_count"
    ].dropna()
    effective_specification_count_range = (
        f"{float(effective_specification_count.min()):.3f}—"
        f"{float(effective_specification_count.max()):.3f}"
    )
    peer_shared_adopted = int(
        detail.loc[
            detail["realtime_peer_shared_status"].eq("adopted"),
            "track_id",
        ].nunique()
    )
    peer_shared_eligible = int(
        detail.loc[detail["realtime_eligible"], "track_id"].nunique()
    )
    peer_shared_positive_rate = (
        summary["realtime_peer_shared_positive_r2_tracks"]
        / summary["realtime_peer_shared_eligible_tracks"]
    )
    peer_shared_positive_rate_range = (
        f"{_rate(float(peer_shared_positive_rate.min()))}—"
        f"{_rate(float(peer_shared_positive_rate.max()))}"
    )
    peer_shared_r2_improvement = summary[
        "median_realtime_peer_shared_r2_improvement"
    ].dropna()
    peer_shared_r2_improvement_range = (
        f"{_rate(float(peer_shared_r2_improvement.min()))}—"
        f"{_rate(float(peer_shared_r2_improvement.max()))}"
    )
    dynamic_factor_adopted = int(
        detail.loc[
            detail["realtime_dynamic_factor_status"].eq("adopted"),
            "track_id",
        ].nunique()
    )
    dynamic_factor_eligible = int(
        detail.loc[detail["realtime_eligible"], "track_id"].nunique()
    )
    dynamic_factor_positive_rate = (
        summary["realtime_dynamic_factor_positive_r2_tracks"]
        / summary["realtime_dynamic_factor_eligible_tracks"]
    )
    dynamic_factor_positive_rate_range = (
        f"{_rate(float(dynamic_factor_positive_rate.min()))}—"
        f"{_rate(float(dynamic_factor_positive_rate.max()))}"
    )
    dynamic_factor_r2_improvement = summary[
        "median_realtime_dynamic_factor_r2_improvement"
    ].dropna()
    dynamic_factor_r2_improvement_range = (
        f"{_rate(float(dynamic_factor_r2_improvement.min()))}—"
        f"{_rate(float(dynamic_factor_r2_improvement.max()))}"
    )
    nearest_factor_adopted = int(
        detail.loc[
            detail["realtime_nearest_factor_status"].eq("adopted"),
            "track_id",
        ].nunique()
    )
    nearest_factor_eligible = int(
        detail.loc[detail["realtime_eligible"], "track_id"].nunique()
    )
    nearest_factor_positive_rate = (
        summary["realtime_nearest_factor_positive_r2_tracks"]
        / summary["realtime_nearest_factor_eligible_tracks"]
    )
    nearest_factor_positive_rate_range = (
        f"{_rate(float(nearest_factor_positive_rate.min()))}—"
        f"{_rate(float(nearest_factor_positive_rate.max()))}"
    )
    nearest_factor_r2_improvement = summary[
        "median_realtime_nearest_factor_r2_improvement"
    ].dropna()
    nearest_factor_r2_improvement_range = (
        f"{_rate(float(nearest_factor_r2_improvement.min()))}—"
        f"{_rate(float(nearest_factor_r2_improvement.max()))}"
    )
    nearest_specification_stable_rate = (
        summary["realtime_nearest_factor_specification_stable_tracks"]
        / summary["realtime_nearest_factor_eligible_tracks"]
    )
    nearest_early_positive_rate = (
        summary["realtime_nearest_factor_positive_early_vintage_tracks"]
        / summary["realtime_nearest_factor_eligible_tracks"]
    )
    nearest_late_positive_rate = (
        summary["realtime_nearest_factor_positive_late_vintage_tracks"]
        / summary["realtime_nearest_factor_eligible_tracks"]
    )
    nearest_specification_stable_rate_range = (
        f"{_rate(float(nearest_specification_stable_rate.min()))}—"
        f"{_rate(float(nearest_specification_stable_rate.max()))}"
    )
    nearest_vintage_positive_rate_range = (
        f"早期{_rate(float(nearest_early_positive_rate.min()))}—"
        f"{_rate(float(nearest_early_positive_rate.max()))}，"
        f"晚期{_rate(float(nearest_late_positive_rate.min()))}—"
        f"{_rate(float(nearest_late_positive_rate.max()))}"
    )
    low_target_variance_tracks = int(
        detail.loc[
            detail["realtime_low_target_variance_warning"].eq(True),
            "track_id",
        ].nunique()
    )
    orthogonal_adopted = int(
        detail.loc[
            detail["realtime_causal_orthogonal_status"].eq("adopted"),
            "track_id",
        ].nunique()
    )
    orthogonal_eligible = int(
        detail.loc[detail["realtime_eligible"], "track_id"].nunique()
    )
    orthogonal_primary_r2 = summary[
        "median_realtime_orthogonal_primary_r2_improvement"
    ].dropna()
    orthogonal_comparison_r2 = summary[
        "median_realtime_orthogonal_comparison_r2_improvement"
    ].dropna()
    orthogonal_primary_r2_range = (
        f"{_rate(float(orthogonal_primary_r2.min()))}—"
        f"{_rate(float(orthogonal_primary_r2.max()))}"
    )
    orthogonal_comparison_r2_range = (
        f"{_rate(float(orthogonal_comparison_r2.min()))}—"
        f"{_rate(float(orthogonal_comparison_r2.max()))}"
    )
    base_maximum_correlation = summary[
        "median_realtime_base_maximum_correlation"
    ].dropna()
    orthogonal_maximum_correlation = summary[
        "median_realtime_orthogonal_maximum_correlation"
    ].dropna()
    orthogonal_uncertainty = summary[
        "median_realtime_orthogonalization_uncertainty_share"
    ].dropna()
    orthogonal_span_uncertainty = summary[
        "median_realtime_orthogonalization_span_uncertainty_share"
    ].dropna()
    orthogonal_uncertainty_range = (
        f"{_rate(float(orthogonal_uncertainty.min()))}—"
        f"{_rate(float(orthogonal_uncertainty.max()))}"
    )
    orthogonal_span_uncertainty_range = (
        f"{_rate(float(orthogonal_span_uncertainty.min()))}—"
        f"{_rate(float(orthogonal_span_uncertainty.max()))}"
    )
    monthly_gain = payload["indicatorContributionStudy"][
        "crossFilterGainCalibration"
    ]["cycles"]
    annual_gain = payload["indicatorContributionStudy"]["longHistory"][
        "crossFilterGainCalibration"
    ]["cycles"]
    monthly_c2_c3_gain = "；".join(
        _gain_calibration_text(cycle_id, monthly_gain[cycle_id])
        for cycle_id in ("C2", "C3")
    )
    annual_c2_c3_gain = "；".join(
        _gain_calibration_text(cycle_id, annual_gain[cycle_id])
        for cycle_id in ("C2", "C3")
    )
    adopted_monthly_cycles = [
        cycle_id
        for cycle_id, calibration in monthly_gain.items()
        if calibration.get("status") == "adopted"
    ]
    report = f"""# 周期指标贡献的跨滤波稳健性

## 结论

- Gaussian FFT 与 Butterworth 在历史中段的路径相关普遍较高，但最新端点的方向和幅度一致率明显更低。
- “严格稳定”要求主模型、对照模型、当前方向、路径相关、点幅度、周期内占比和解释方差差异全部通过，因此稳定率低于任一单项通过率。
- 失败原因允许重叠；不能把低稳定率解释为“周期不存在”，只能说明当前点不足以发布为确定贡献。
- C2、C3月频轨道仍受三轮完整历史限制；长周期应优先查看年频层，并继续保留预处理敏感性警告。
- 固定跨滤波增益挑战者按每条轨道前60%训练、中间20%验证、末20%独立审计，并按周期跨轨道共享一个倍率。月频：{monthly_c2_c3_gain}。年频：{annual_c2_c3_gain}。C2/C3均未达到采用门槛，说明统一幅度倍率不能解锁长周期；同一规则下月频{'+'.join(adopted_monthly_cycles)}通过，表明门槛具备区分力。
- 因果端点确认使用灵敏、基准、平滑三组全局阻尼谐波状态空间参数，并按当时之前的一步创新误差动态加权；权重规则和上下限全局固定，不使用最终回溯路径调权。模型同时进行最多12个历史截点滚动重训。当前点使用前一期以前的数据拟合，总不确定性合并状态滤波误差、滚动系数漂移和状态参数集差异。它分解当前已观测指标，不预测下一期。
- 当前各周期系数漂移误差中位仅占总不确定性的{coefficient_uncertainty_range}，状态空间参数集差异占{state_specification_uncertainty_range}；端点幅度对状态提取参数明显比对Ridge系数更敏感。
- 动态权重在{dynamic_improvement_rate_range}的可比较轨道上优于同截点等权中位，滚动重构R²中位增量为{dynamic_r2_improvement_range}；有效参数数仍为{effective_specification_count_range}/3，说明证据支持轻微自适应，而不支持押注单一参数档。
- 类别→组别→全局的留一法家族共享仅在{peer_shared_positive_rate_range}的可比较轨道上取得正R²增益，各周期中位增量为{peer_shared_r2_improvement_range}；按“R²至少提升1个百分点、MAE不恶化、方向不下降”门槛，仅{peer_shared_adopted}/{peer_shared_eligible}条轨道晋级。共享参数不是当前主要解锁点。
- 留一同业动态因子使用滞后滚动相关对齐方向与尺度，并以不高于35%的固定权重收缩单轨道状态；仅{dynamic_factor_positive_rate_range}的轨道取得正R²增益，各周期中位增量为{dynamic_factor_r2_improvement_range}，最终{dynamic_factor_adopted}/{dynamic_factor_eligible}条轨道在联合重构层晋级。C2/C3各有2条包含该周期的轨道级局部晋级，但这不是单周期独立证明，且多数长周期轨道的R²与MAE恶化，因此不能解除整体阻断。
- 因果近邻因子主规格在每个时点只使用此前窗口内绝对相关最高、且相关不低于0.20的3条留一同业轨道；预先固定的5近邻和1.5倍相关窗口只做稳定性审计。{nearest_factor_positive_rate_range}的可比较轨道取得正R²增益，各周期中位增量为{nearest_factor_r2_improvement_range}，{nearest_factor_adopted}/{nearest_factor_eligible}条轨道同时通过R²、MAE与方向门槛。三规格采用/拒绝一致率为{nearest_specification_stable_rate_range}；规格分歧计入端点不确定性，不能通过回看结果选择最优规格。
- 同一主规格按滚动截点前后半段复核，正R²增益覆盖为{nearest_vintage_positive_rate_range}。C2早期仅1/5为正且中位-7.6%，晚期4/5为正且中位+6.9%；C3早期1/7为正且中位-4.0%，晚期5/7为正且中位+3.4%。改善明显集中在近期，不能解除C2/C3阻断。
- {low_target_variance_tracks}条GDP分项在12个滚动截点上的目标方差接近零，使R²增量出现极端正负值；系统现已显式标记并禁止这些轨道依赖R²晋级。横截面结论只对可比较轨道使用中位数、正增益覆盖和三门槛晋级数，不使用R²均值。
- 长周期→短周期的因果动态正交显著降低状态重叠：各周期最大相关中位由{float(base_maximum_correlation.min()):.3f}—{float(base_maximum_correlation.max()):.3f}降至{float(orthogonal_maximum_correlation.min()):.3f}—{float(orthogonal_maximum_correlation.max()):.3f}。60期主规格滚动R²中位增量为{orthogonal_primary_r2_range}，120期对照为{orthogonal_comparison_r2_range}；双规格复核后{orthogonal_adopted}/{orthogonal_eligible}条轨道晋级。
- 正交模型晋级后，相对基础模型的差异占总不确定性中位{orthogonal_uncertainty_range}，60/120期跨度差异占{orthogonal_span_uncertainty_range}。因此确认数量下降不是模型失效，而是原先由频带重叠支撑的弱确认被重新计入模型风险。

## 月频104轨道

{_markdown_table(display, [
    "cycle_id",
    "eligible_tracks",
    "stable_tracks",
    "stable_rate",
    "primary_model_pass_rate",
    "comparison_model_pass_rate",
    "direction_pass_rate",
    "path_pass_rate",
    "point_amplitude_pass_rate",
    "share_pass_rate",
    "variance_pass_rate",
    "median_path_correlation",
])}

## 因果端点确认

{_markdown_table(display, [
    "cycle_id",
    "realtime_eligible_tracks",
    "realtime_confirmed_tracks",
    "realtime_confirmed_rate",
    "median_realtime_rolling_direction_agreement",
    "median_realtime_rolling_correlation",
    "median_realtime_coefficient_sign_agreement",
    "median_realtime_coefficient_uncertainty_share",
    "median_realtime_rolling_state_specification_direction_agreement",
    "median_realtime_state_specification_uncertainty_share",
    "median_realtime_responsive_weight",
    "median_realtime_baseline_weight",
    "median_realtime_smooth_weight",
    "median_realtime_state_specification_effective_count",
    "realtime_dynamic_weight_improved_tracks",
    "median_realtime_dynamic_weight_r2_improvement",
    "realtime_peer_shared_adopted_tracks",
    "realtime_peer_shared_positive_r2_tracks",
    "median_realtime_peer_shared_r2_improvement",
    "realtime_dynamic_factor_adopted_tracks",
    "realtime_dynamic_factor_positive_r2_tracks",
    "median_realtime_dynamic_factor_r2_improvement",
    "realtime_nearest_factor_adopted_tracks",
    "realtime_nearest_factor_positive_r2_tracks",
    "median_realtime_nearest_factor_r2_improvement",
    "realtime_nearest_factor_specification_stable_tracks",
    "realtime_nearest_factor_robustly_adopted_tracks",
    "realtime_nearest_factor_positive_early_vintage_tracks",
    "realtime_nearest_factor_positive_late_vintage_tracks",
    "median_realtime_nearest_factor_early_vintage_r2_improvement",
    "median_realtime_nearest_factor_late_vintage_r2_improvement",
    "realtime_low_target_variance_warning_tracks",
    "realtime_causal_orthogonal_adopted_tracks",
    "median_realtime_orthogonal_primary_r2_improvement",
    "median_realtime_orthogonal_comparison_r2_improvement",
    "median_realtime_base_maximum_correlation",
    "median_realtime_orthogonal_maximum_correlation",
    "median_realtime_base_condition_number",
    "median_realtime_orthogonal_condition_number",
    "median_realtime_orthogonalization_uncertainty_share",
    "median_realtime_orthogonalization_span_uncertainty_share",
    "median_realtime_absolute_revision",
    "median_realtime_rolling_reconstruction_r2",
    "median_realtime_signal_to_uncertainty",
])}

## 年频长历史

{_markdown_table(annual_display, list(annual_display.columns))}

## 门槛定义

- 路径相关不低于0.70，并剔除双边滤波两端。
- 当前点相对幅度差不高于0.75。
- 周期内绝对占比差不高于0.15。
- 近120期Shapley解释方差差不高于0.15。
- 两套Ridge重构都需通过时间分块与系数符号稳定要求。
- 因果端点确认至少需要8个滚动截点，滚动重构R²大于0、方向一致率不低于0.60、贡献相关不低于0.30、滚动系数同号率不低于0.60、三组状态参数当前及历史同向率均不低于2/3、当前合并信号/不确定性不低于0.50。
- 家族共享挑战者至少需要3条留一法同类轨道；类别不足时依次回退到市场/经济组和全局池。共享误差权重不高于50%，且只有滚动R²至少提升0.01、方向准确率不低于50%并且不下降、MAE不恶化时才替代单轨道权重。
- 因果近邻挑战者只使用前一期以前的状态计算滚动相关，每期最多选择3条绝对相关不低于0.20的轨道；同样要求滚动R²至少提升0.01、方向不下降且MAE不恶化。选择过程不读取最终回溯路径。
- 因果近邻的5近邻和1.5倍相关窗口是预先固定的审计规格，不参与择优；只有三套规格都采用时主规格才可晋级。规格点估计分歧计入总不确定性。
- 当12个滚动截点目标方差低于全历史目标方差的1%时，标记低目标方差警告；该轨道的R²和R²增量不参与挑战者晋级与横截面汇总。
- 因果正交按长周期到短周期顺序，使用截至前一期的60期EWM协方差估计并保留固定Ridge稳定项；120期跨度作为对照。主规格R²至少提升0.01，对照规格不得恶化，二者MAE和方向均不得恶化，且最大相关和条件数必须下降。
- 正交模型晋级后，单周期确认还要求60/120期贡献当前同向、滚动同向率不低于2/3、滚动相关不低于0.50；模型差异和跨度差异均计入总不确定性。

本报告属于回溯频带诊断，不是经济因果归因、实时交易信号或资产配置权重。
"""
    return detail, summary, report


def main() -> None:
    detail, summary, report = build_report()
    DETAIL_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(DETAIL_OUTPUT, index=False)
    summary.to_csv(SUMMARY_OUTPUT, index=False)
    REPORT_OUTPUT.write_text(report, encoding="utf-8")
    print(
        json.dumps(
            {
                "detail": str(DETAIL_OUTPUT.relative_to(ROOT)),
                "summary": str(SUMMARY_OUTPUT.relative_to(ROOT)),
                "report": str(REPORT_OUTPUT.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
